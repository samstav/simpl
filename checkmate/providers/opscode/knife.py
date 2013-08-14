'''
Module to handle OpsCode Chef `knife` command-line calls

TODO:
- many functions too complex
- split out celery handling from knife logic

'''
import errno
import hashlib
import json
import logging
import os
import shutil
import subprocess
from subprocess import (  # noqa
    CalledProcessError,
)
import time
import urlparse

from celery.exceptions import (  # noqa
    SoftTimeLimitExceeded,
)
from celery.task import task
from Crypto.PublicKey import RSA
from Crypto.Random import atfork
from eventlet.green import threading

from checkmate import ssh
from checkmate import utils
from checkmate.common import config, statsd
from checkmate.exceptions import (
    BLUEPRINT_ERROR,
    CheckmateException,
    CheckmateCalledProcessError,
    CheckmateUserException,
    UNEXPECTED_ERROR,
)
from checkmate.deployments import (
    resource_postback,
    update_all_provider_resources,
)

LOG = logging.getLogger(__name__)
CONFIG = config.current()


def register_scheme(scheme):
    '''Use this to register a new scheme with urlparse.

    New schemes will be parsed in the same way as http is parsed
    '''
    for method in filter(lambda s: s.startswith('uses_'), dir(urlparse)):
        getattr(urlparse, method).append(scheme)

register_scheme('git')  # without this, urlparse won't handle git:// correctly


def _get_root_environments_path(dep_id, path=None):
    '''Build the path using provided inputs.

    Use any environment variables or configuration settings
    '''
    root = path or CONFIG.deployments_path
    if not os.path.exists(root):
        msg = "Invalid root path: %s" % root
        raise CheckmateUserException(msg, utils.get_class_name(
            CheckmateException), UNEXPECTED_ERROR, '')
    return root


def _run_ruby_command(dep_id, path, command, params, lock=True):
    '''Runs a knife-like command (ex. librarian-chef).

    Since knife-ike command errors are returned to stderr, we need to capture
    stderr and check for errors.

    That needs to be run in a kitchen, so we move curdir and need to make sure
    we stay there, so I added some synchronization code while that takes place
    However, if code calls in that already has a lock, the optional lock param
    can be set to false so thise code does not lock.
    :param version_param: the parameter used to get the command's version. This
            is used to check if the program is installed.
    '''
    params.insert(0, command)
    LOG.debug("Running: '%s' in path '%s'", ' '.join(params), path)
    if lock:
        path_lock = threading.Lock()
        path_lock.acquire()
        try:
            if path:
                os.chdir(path)
            result = subprocess.check_output(params)
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                # Check if command is installed
                output = None
                try:
                    output = subprocess.check_output(['which', command])
                except CalledProcessError:
                    pass
                if not output:
                    msg = ("'%s' is not installed or not accessible on the "
                           "server" % command)
                    raise CheckmateUserException(msg, utils.get_class_name(
                        CheckmateException), UNEXPECTED_ERROR, '')
            raise exc
        except CalledProcessError, exc:
            #retry and pass ex
            # CalledProcessError cannot be serialized using Pickle,
            # so raising it would fail in celery; we wrap the exception in
            # something  Pickle-able.
            msg = exc.output
            raise CheckmateCalledProcessError(exc.returncode, exc.cmd,
                                              output=msg)
        finally:
            path_lock.release()
    else:
        if path:
            os.chdir(path)
        result = subprocess.check_output(params)
    LOG.debug(result)
    return result


def _run_kitchen_command(dep_id, kitchen_path, params, lock=True):
    '''Runs the 'knife xxx' command.

    This also needs to handle knife command errors, which are returned to
    stderr.

    That needs to be run in a kitchen, so we move curdir and need to make sure
    we stay there, so I added some synchronization code while that takes place
    However, if code calls in that already has a lock, the optional lock param
    can be set to false so thise code does not lock
    '''
    LOG.debug("Running: '%s' in path '%s'", ' '.join(params), kitchen_path)
    if '-c' not in params:
        config_file = os.path.join(kitchen_path, 'solo.rb')
        if os.path.exists(config_file):
            LOG.warning("Knife command called without a '-c' flag. The '-c' "
                        "flag is a strong safeguard in case knife runs in the "
                        "wrong directory. Consider adding it and pointing to "
                        "solo.rb")
            LOG.debug("Defaulting to config file '%s'", config_file)
            params.extend(['-c', config_file])
    result = _run_ruby_command(dep_id, kitchen_path, params[0], params[1:],
                               lock=lock)

    # Knife succeeds even if there is an error. This code tries to parse the
    # output to return a useful error. Note that FATAL erros will be picked up
    # by _run_ruby_command
    last_error = ''
    for line in result.split('\n'):
        if 'ERROR:' in line:
            LOG.error(line)
            last_error = line
    if last_error:
        if 'KnifeSolo::::' in last_error:
            # Get the string after a Knife-Solo error::
            error = last_error.split('Error:')[-1]
            if error:
                msg = "Knife error encountered: %s" % error
                raise CheckmateCalledProcessError(1, ' '.join(params),
                                                  output=msg)
            # Don't raise on all errors. They don't all mean failure!
    return result


def _create_environment_keys(dep_id, environment_path, private_key=None,
                             public_key_ssh=None):
    '''Put keys in an existing environment

    If none are provided, a new set of public/private keys are created
    '''
    # Create private key
    private_key_path = os.path.join(environment_path, 'private.pem')
    if os.path.exists(private_key_path):
        # Already exists.
        if private_key:
            with file(private_key_path, 'r') as pk_file:
                data = pk_file.read()
            if data != private_key:
                msg = ("A private key already exists in environment %s and "
                       "does not match the value provided" % environment_path)
                raise CheckmateUserException(msg, utils.get_class_name(
                    CheckmateException), UNEXPECTED_ERROR, '')
    else:
        if private_key:
            with file(private_key_path, 'w') as pk_file:
                pk_file.write(private_key)
            LOG.debug("Wrote environment private key: %s", private_key_path)
        else:
            params = ['openssl', 'genrsa', '-out', private_key_path, '2048']
            result = subprocess.check_output(params)
            LOG.debug(result)
            LOG.debug("Generated environment private key: %s",
                      private_key_path)

    # Secure private key
    os.chmod(private_key_path, 0600)
    LOG.debug("Private cert permissions set: chmod 0600 %s", private_key_path)

    # Get or Generate public key
    public_key_path = os.path.join(environment_path, 'checkmate.pub')
    if os.path.exists(public_key_path):
        LOG.debug("Public key exists. Retrieving it from %s", public_key_path)
        with file(public_key_path, 'r') as public_key_file_r:
            public_key_ssh = public_key_file_r.read()
    else:
        if not public_key_ssh:
            params = ['ssh-keygen', '-y', '-f', private_key_path]
            public_key_ssh = subprocess.check_output(params)
            LOG.debug("Generated environment public key: %s", public_key_path)
        # Write it to environment
        with file(public_key_path, 'w') as public_key_file_w:
            public_key_file_w.write(public_key_ssh)
        LOG.debug("Wrote environment public key: %s", public_key_path)
    return dict(public_key_ssh=public_key_ssh, public_key_path=public_key_path,
                private_key_path=private_key_path)


def _write_knife_config_file(kitchen_path):
    '''Writes a solo.rb config file and links a knife.rb file too.'''
    secret_key_path = os.path.join(kitchen_path, 'certificates', 'chef.pem')
    config = """# knife -c knife.rb
file_cache_path  "%s"
cookbook_path    ["%s", "%s"]
role_path  "%s"
data_bag_path  "%s"
log_level        :info
log_location     "%s"
verbose_logging  true
ssl_verify_mode  :verify_none
encrypted_data_bag_secret "%s"
""" % (kitchen_path,
       os.path.join(kitchen_path, 'cookbooks'),
       os.path.join(kitchen_path, 'site-cookbooks'),
       os.path.join(kitchen_path, 'roles'),
       os.path.join(kitchen_path, 'data_bags'),
       os.path.join(kitchen_path, 'knife-solo.log'),
       secret_key_path)
    # knife kitchen creates a default solo.rb, so the file already exists
    solo_file = os.path.join(kitchen_path, 'solo.rb')
    with file(solo_file, 'w') as handle:
        handle.write(config)
    LOG.debug("Created solo file: %s", solo_file)
    return (solo_file, secret_key_path)


def _get_blueprints_cache_path(source_repo):
    '''Return the path of the blueprint cache directory.'''
    utils.match_celery_logging(LOG)
    LOG.debug("source_repo: %s", source_repo)
    prefix = CONFIG.deployments_path
    suffix = hashlib.md5(source_repo).hexdigest()
    return os.path.join(prefix, "cache", "blueprints", suffix)


def _cache_blueprint(source_repo):
    '''Cache a blueprint repo or update an existing cache, if necessary.'''
    LOG.debug("(cache) Running providers.opscode.knife._cache_blueprint()...")
    cache_expire_time = os.environ.get("CHECKMATE_BLUEPRINT_CACHE_EXPIRE")
    if not cache_expire_time:
        cache_expire_time = 3600
        LOG.info("(cache) CHECKMATE_BLUEPRINT_CACHE_EXPIRE variable not set. "
                 "Defaulting to %s", cache_expire_time)
    cache_expire_time = int(cache_expire_time)
    repo_cache = _get_blueprints_cache_path(source_repo)
    if "#" in source_repo:
        url, branch = source_repo.split("#")
    else:
        url = source_repo
        branch = "master"
    if os.path.exists(repo_cache):  # Cache exists
        # The mtime of .git/FETCH_HEAD changes upon every "git
        # fetch".  FETCH_HEAD is only created after the first
        # fetch, so use HEAD if it's not there
        if os.path.isfile(os.path.join(repo_cache, ".git", "FETCH_HEAD")):
            head_file = os.path.join(repo_cache, ".git", "FETCH_HEAD")
        else:
            head_file = os.path.join(repo_cache, ".git", "HEAD")
        last_update = time.time() - os.path.getmtime(head_file)
        LOG.debug("(cache) cache_expire_time: %s", cache_expire_time)
        LOG.debug("(cache) last_update: %s", last_update)

        if last_update > cache_expire_time:  # Cache miss
            LOG.debug("(cache) Updating repo: %s", repo_cache)
            tags = utils.git_tags(repo_cache)
            if branch in tags:
                tag = branch
                refspec = "refs/tags/" + tag + ":refs/tags/" + tag
                try:
                    utils.git_fetch(repo_cache, refspec)
                    utils.git_checkout(repo_cache, tag)
                except CalledProcessError as exc:
                    LOG.info("Unable to update git tags from the git "
                             "repository at %s.  Using the cached repository",
                             url)
            else:
                try:
                    utils.git_pull(repo_cache, branch)
                except CalledProcessError as exc:
                    LOG.info("Unable to pull from git repository at %s.  "
                             "Using the cached repository", url)
        else:  # Cache hit
            LOG.debug("(cache) Using cached repo: %s", repo_cache)
    else:  # Cache does not exist
        LOG.debug("(cache) Cloning repo to %s", repo_cache)
        os.makedirs(repo_cache)
        try:
            utils.git_clone(repo_cache, url, branch=branch)
        except CalledProcessError as exc:
            error_message = "Git repository could not be cloned " \
                 "from '%s'.  The error returned was " \
                 "'%s'"
            raise CheckmateUserException(error_message, utils.get_class_name(
                CheckmateException), UNEXPECTED_ERROR, '')
        tags = utils.git_tags(repo_cache)
        if branch in tags:
            tag = branch
            utils.git_checkout(repo_cache, tag)


def _blueprint_exists(source, dest):
    '''Check that all files in the source blueprint exist in the destination.
    '''
    for source_file in os.listdir(source):
        dest_file = os.path.join(dest, source_file)
        if not os.path.exists(dest_file):
            return False
    return True


def _ensure_kitchen_blueprint(dest, source_repo):
    '''Update the blueprint cache and copy the blueprint to the kitchen.

    Arguments:
    - `dest`: Path to the kitchen
    - `source_repo`: URL of the git-hosted blueprint
    '''
    utils.match_celery_logging(LOG)
    _cache_blueprint(source_repo)
    repo_cache = _get_blueprints_cache_path(source_repo)
    if not os.path.exists(repo_cache):
        message = "No blueprint repository found in %s" % repo_cache
        raise CheckmateUserException(message, utils.get_class_name(
            CheckmateException), UNEXPECTED_ERROR, '')
    LOG.debug("repo_cache: %s", repo_cache)
    LOG.debug("dest: %s", dest)
    if not _blueprint_exists(repo_cache, dest):
        utils.copy_contents(repo_cache,
                            dest,
                            create_path=True,
                            with_overwrite=True)


def _create_kitchen(dep_id, service_name, path, secret_key=None,
                    source_repo=None):
    '''Creates a new knife-solo kitchen in path

    Arguments:
    - `name`: The name of the kitchen
    - `path`: Where to create the kitchen
    - `source_repo`: URL of the git-hosted blueprint
    - `secret_key`: PEM-formatted private key for data bag encryption
    '''
    utils.match_celery_logging(LOG)
    if not os.path.exists(path):
        error_message = "Invalid path: %s" % path
        raise CheckmateUserException(error_message, utils.get_class_name(
            CheckmateException), UNEXPECTED_ERROR, '')

    kitchen_path = os.path.join(path, 'kitchen')

    if not os.path.exists(kitchen_path):
        os.mkdir(kitchen_path, 0770)
        LOG.debug("Created kitchen directory: %s", kitchen_path)
    else:
        LOG.debug("Kitchen directory exists: %s", kitchen_path)

    nodes_path = os.path.join(kitchen_path, 'nodes')
    if os.path.exists(nodes_path):
        if any((f.endswith('.json') for f in os.listdir(nodes_path))):
            msg = ("Kitchen already exists and seems to have nodes defined "
                   "in it: %s" % nodes_path)
            LOG.debug(msg)
            return {"kitchen": kitchen_path}
    else:
        # we don't pass the config file here because we're creating the
        # kitchen for the first time and knife will overwrite our config file
        params = ['knife', 'solo', 'init', '.']
        _run_kitchen_command(dep_id, kitchen_path, params)

    solo_file, secret_key_path = _write_knife_config_file(kitchen_path)

    # Create bootstrap.json in the kitchen
    bootstrap_path = os.path.join(kitchen_path, 'bootstrap.json')
    if not os.path.exists(bootstrap_path):
        with file(bootstrap_path, 'w') as f:
            json.dump({"run_list": ["recipe[build-essential]"]}, f)

    # Create certificates folder
    certs_path = os.path.join(kitchen_path, 'certificates')
    if os.path.exists(certs_path):
        LOG.debug("Certs directory exists: %s", certs_path)
    else:
        os.mkdir(certs_path, 0770)
        LOG.debug("Created certs directory: %s", certs_path)

    # Store (generate if necessary) the secrets file
    if os.path.exists(secret_key_path):
        if secret_key:
            with file(secret_key_path, 'r') as secret_key_file_r:
                data = secret_key_file_r.read(secret_key)
            if data != secret_key:
                msg = ("Kitchen secrets key file '%s' already exists and does "
                       "not match the provided value" % secret_key_path)
                raise CheckmateUserException(msg, utils.get_class_name(
                    CheckmateException), UNEXPECTED_ERROR, '')
        LOG.debug("Stored secrets file exists: %s", secret_key_path)
    else:
        if not secret_key:
            # celery runs os.fork(). We need to reset the random number
            # generator before generating a key. See atfork.__doc__
            atfork()
            key = RSA.generate(2048)
            secret_key = key.exportKey('PEM')
            LOG.debug("Generated secrets private key")
        with file(secret_key_path, 'w') as secret_key_file_w:
            secret_key_file_w.write(secret_key)
        LOG.debug("Stored secrets file: %s", secret_key_path)

    # Knife defaults to knife.rb, but knife-solo looks for solo.rb, so we link
    # both files so that knife and knife-solo commands will work and anyone
    # editing one will also change the other
    knife_file = os.path.join(kitchen_path, 'knife.rb')
    if os.path.exists(knife_file):
        LOG.debug("Knife.rb already exists: %s", knife_file)
    else:
        os.link(solo_file, knife_file)
        LOG.debug("Linked knife.rb: %s", knife_file)

    # Copy blueprint files to kitchen
    if source_repo:
        _ensure_kitchen_blueprint(kitchen_path, source_repo)

    LOG.debug("Finished creating kitchen: %s", kitchen_path)
    return {"kitchen": kitchen_path}


@task
@statsd.collect
def write_databag(environment, bagname, itemname, contents, resource,
                  path=None, secret_file=None, merge=True,
                  kitchen_name='kitchen'):
    '''Updates a data_bag or encrypted_data_bag

    :param environment: the ID of the environment
    :param bagname: the name of the databag (in solo, this ends up being a
            directory)
    :param item: the name of the item (in solo this ends up being a .json file)
    :param contents: this is a dict of attributes to write in to the databag
    :param path: optional override to the default path where environments live
    :param secret_file: the path to a certificate used to encrypt a data_bag
    :param merge: if True, the data will be merged in. If not, it will be
            completely overwritten
    :param kitchen_name: Optional name of kitchen to write to.  default=kitchen
    '''
    utils.match_celery_logging(LOG)

    #TODO: add context
    if utils.is_simulation(environment):
        return

    def on_failure(exc, task_id, args, kwargs, einfo):
        '''Handle task failure.'''
        if args and len(args) >= 3:
            resource = args[2]
            dep_id = args[1]
            host = args[0]
            if resource:
                k = "instance:%s" % resource.get('index')
                host_k = "instance:%s" % resource.get('hosted_on')
                ret = {}
                ret.update({
                    k: {
                        'status': 'ERROR',
                        'error-message': (
                            'Error writing software configuration '
                            'to host %s: %s' % (host, exc.args[0])
                        )
                    }
                })
                if host_k:
                    ret.update({
                        host_k: {
                            'status': 'ERROR',
                            'error-message': (
                                'Error installing software resource %s' %
                                resource.get('index')
                            )
                        }
                    })
                resource_postback.delay(dep_id, ret)
        else:
            LOG.warn("Error callback for cook task %s did not get appropriate "
                     "args", task_id)

    write_databag.on_failure = on_failure

    root = _get_root_environments_path(environment, path)

    kitchen_path = os.path.join(root, environment, kitchen_name)
    databags_root = os.path.join(kitchen_path, 'data_bags')
    if not os.path.exists(databags_root):
        msg = ("Data bags path does not exist: %s" % databags_root)
        raise CheckmateUserException(msg, utils.get_class_name(
            CheckmateException), UNEXPECTED_ERROR, '')
    # Check if the bag already exists (create it if not)
    config_file = os.path.join(kitchen_path, 'solo.rb')
    params = ['knife', 'solo', 'data', 'bag', 'list', '-F', 'json',
              '-c', config_file]
    data_bags = _run_kitchen_command(environment, kitchen_path, params)
    if data_bags:
        data_bags = json.loads(data_bags)
    if bagname not in data_bags:
        merge = False  # Nothing to merge if it is new!
        _run_kitchen_command(environment, kitchen_path,
                             ['knife', 'solo', 'data', 'bag', 'create',
                              bagname, '-c', config_file])
        LOG.debug("Created data bag '%s' in '%s'", bagname, databags_root)

    # Check if the item already exists (create it if not)
    params = ['knife', 'solo', 'data', 'bag', 'show', bagname, '-F', 'json',
              '-c', config_file]
    existing_contents = _run_kitchen_command(environment, kitchen_path, params)
    if existing_contents:
        existing_contents = json.loads(existing_contents)
    if itemname not in existing_contents:
        merge = False  # Nothing to merge if it is new!

    # Write contents
    if merge:
        params = ['knife', 'solo', 'data', 'bag', 'show', bagname, itemname,
                  '-F', 'json', '-c', config_file]
        if secret_file:
            params.extend(['--secret-file', secret_file])

        lock = threading.Lock()
        lock.acquire()
        try:
            data = _run_kitchen_command(environment, kitchen_path, params)
            if data:
                existing = json.loads(data)
                contents = utils.merge_dictionary(existing, contents)
            if isinstance(contents, dict):
                contents = json.dumps(contents)
            params = ['knife', 'solo', 'data', 'bag', 'create', bagname,
                      itemname, '-c', config_file, '-d', '--json', contents]
            if secret_file:
                params.extend(['--secret-file', secret_file])
            result = _run_kitchen_command(environment, kitchen_path, params,
                                          lock=False)
        except CalledProcessError, exc:
            # Reraise pickleable exception
            raise CheckmateCalledProcessError(exc.returncode, exc.cmd,
                                              output=msg)
        finally:
            lock.release()
        LOG.debug(result)
    else:
        if contents:
            if 'id' not in contents:
                contents['id'] = itemname
            elif contents['id'] != itemname:
                message = ("The value of the 'id' field in a "
                           "databag item is reserved by Chef "
                           "and must be set to the name of the "
                           "databag item. Checkmate will set "
                           "this for you if it is missing, but "
                           "the data you supplied included an "
                           "ID that did not match the databag "
                           "item name. The ID was '%s' and the "
                           "databag item name was '%s'" % (contents['id'],
                                                           itemname))
                raise CheckmateUserException(message, utils.get_class_name(
                    CheckmateException), UNEXPECTED_ERROR, '')
            if isinstance(contents, dict):
                contents = json.dumps(contents)
            params = ['knife', 'solo', 'data', 'bag', 'create', bagname,
                      itemname, '-d', '-c', config_file, '--json', contents]
            if secret_file:
                params.extend(['--secret-file', secret_file])
            result = _run_kitchen_command(environment, kitchen_path, params)
            LOG.debug(result)
        else:
            LOG.warning("write_databag was called with no contents")


@task(countdown=20, max_retries=3)
@statsd.collect
def cook(host, environment, resource, recipes=None, roles=None, path=None,
         username='root', password=None, identity_file=None, port=22,
         attributes=None, kitchen_name='kitchen'):
    '''Apply recipes/roles to a server'''
    utils.match_celery_logging(LOG)

    #TODO: add context
    if utils.is_simulation(environment):
        pb_res = {}
        # Update status of host resource to ACTIVE
        host_results = {}
        host_results['status'] = "ACTIVE"
        host_key = 'instance:%s' % resource['hosted_on']
        host_results = {host_key: host_results}
        pb_res.update(host_results)

        # Update status of current resource to ACTIVE
        results = {}
        results['status'] = "ACTIVE"
        instance_key = 'instance:%s' % resource['index']
        results = {instance_key: results}
        pb_res.update(results)

        resource_postback.delay(environment, pb_res)
        return

    def on_failure(exc, task_id, args, kwargs, einfo):
        '''Handle task failure.'''
        if args and len(args) >= 3:
            resource = args[2]
            dep_id = args[1]
            host = args[0]
            if resource:
                k = "instance:%s" % resource.get('index')
                host_k = "instance:%s" % resource.get('hosted_on')
                ret = {}
                ret.update({
                    k: {
                        'status': 'ERROR',
                        'error-message': (
                            'Error installing software on host %s' % host
                        )
                    }
                })
                if host_k:
                    ret.update({
                        host_k: {
                            'status': 'ERROR',
                            'error-message': (
                                'Error installing software resource %s' %
                                resource.get('index')
                            )
                        }
                    })
                resource_postback.delay(dep_id, ret)
        else:
            LOG.warn("Error callback for cook task %s did not get appropriate "
                     "args", task_id)

    cook.on_failure = on_failure

    # Server provider updates status to CONFIGURE, but sometimes the server is
    # configured twice, so we need to do this update anyway just to be safe
    # Update status of host resource to CONFIGURE
    res = {}
    host_results = {}
    host_results['status'] = "CONFIGURE"
    host_key = 'instance:%s' % resource['hosted_on']
    host_results = {host_key: host_results}
    res.update(host_results)

    # Update status of current resource to BUILD
    results = {}
    results['status'] = "BUILD"
    instance_key = 'instance:%s' % resource['index']
    results = {instance_key: results}
    res.update(results)

    resource_postback.delay(environment, res)

    root = _get_root_environments_path(environment, path)

    kitchen_path = os.path.join(root, environment, kitchen_name)
    if not os.path.exists(kitchen_path):
        message = "Environment kitchen does not exist: %s" % kitchen_path
        raise CheckmateUserException(message, utils.get_class_name(
            CheckmateException), UNEXPECTED_ERROR, '')
    node_path = os.path.join(kitchen_path, 'nodes', '%s.json' % host)
    if not os.path.exists(node_path):
        cook.retry(exc=CheckmateException("Node '%s' is not registered in %s"
                                          % (host, kitchen_path)))

    # Add any missing recipes to node settings
    run_list = []
    if roles:
        run_list.extend(["role[%s]" % role for role in roles])
    if recipes:
        run_list.extend(["recipe[%s]" % recipe for recipe in recipes])
    if run_list or attributes:
        add_list = []
        # Open file, read/parse/calculate changes, then write
        lock = threading.Lock()
        lock.acquire()
        try:
            with file(node_path, 'r') as node_file_r:
                node = json.load(node_file_r)
            if run_list:
                for entry in run_list:
                    if entry not in node['run_list']:
                        node['run_list'].append(entry)
                        add_list.append(entry)
            if attributes:
                utils.merge_dictionary(node, attributes)
            if add_list or attributes:
                with file(node_path, 'w') as node_file_w:
                    json.dump(node, node_file_w)
        finally:
            lock.release()
        if add_list:
            LOG.debug("Added to %s: %s", node_path, add_list)
        else:
            LOG.debug("All run_list already exists in %s: %s", node_path,
                      run_list)
        if attributes:
            LOG.debug("Wrote attributes to %s", node_path,
                      extra={'data': attributes})
    else:
        LOG.debug("No recipes or roles to add and no attribute changes. Will "
                  "just run 'knife cook' for %s using bootstrap.json",
                  node_path)

    # Build and run command
    if not username:
        username = 'root'
    params = ['knife', 'solo', 'cook', '%s@%s' % (username, host),
              '-c', os.path.join(kitchen_path, 'solo.rb')]
    if not (run_list or attributes):
        params.extend(['bootstrap.json'])
    if identity_file:
        params.extend(['-i', identity_file])
    if password:
        params.extend(['-P', password])
    if port:
        params.extend(['-p', str(port)])
    try:
        _run_kitchen_command(environment, kitchen_path, params)
        LOG.info("Knife cook succeeded for %s in %s", host, environment)
    except (CalledProcessError, CheckmateCalledProcessError) as exc:
        LOG.warn("Knife cook failed for %s. Retrying.", host)
        cook.retry(exc=exc)

    # TODO: When hosted_on resource can host more than one resource, need to
    # make sure all other hosted resources are ACTIVE before we can change
    # hosted_on resource itself to ACTIVE
    pb_res = {}
    # Update status of host resource to ACTIVE
    host_results = {}
    host_results['status'] = "ACTIVE"
    host_key = 'instance:%s' % resource['hosted_on']
    host_results = {host_key: host_results}
    pb_res.update(host_results)

    # Update status of current resource to ACTIVE
    results = {}
    results['status'] = "ACTIVE"
    instance_key = 'instance:%s' % resource['index']
    results = {instance_key: results}
    pb_res.update(results)

    resource_postback.delay(environment, pb_res)


def _ensure_berkshelf_environment():
    '''Checks the Berkshelf environment and sets it up if necessary.'''
    berkshelf_path = CONFIG.berkshelf_path
    if not berkshelf_path:
        local_path = CONFIG.deployments_path
        if not local_path:
            local_path = "/var/local/checkmate/deployments"
            LOG.warning("CHECKMATE_CHEF_LOCAL_PATH not defined. Using "
                        "%s", local_path)
        berkshelf_path = os.path.join(os.path.dirname(local_path), "cache")
        LOG.warning("BERKSHELF_PATH variable not set. Defaulting "
                    "to %s", berkshelf_path)
    if 'BERKSHELF_PATH' not in os.environ:
        # Berkshelf relies on this being set as an environent variable
        os.environ["BERKSHELF_PATH"] = berkshelf_path
    if not os.path.exists(berkshelf_path):
        os.makedirs(berkshelf_path)
        LOG.info("Created berkshelf_path: %s", berkshelf_path)


@task
def delete_environment(name, path=None):
    root = _get_root_environments_path(name, path)
    full_path = os.path.join(root, name)
    try:
        shutil.rmtree(full_path)
        LOG.debug("Removed environment directory: %s", full_path)
    except OSError as ose:
        if ose.errno == errno.ENOENT:
            LOG.warn("Environment directory %s does not exist", full_path,
                     exc_info=True)
        else:
            msg = "Could not delete environment %s", full_path
            raise CheckmateUserException(msg, utils.get_class_name(
                CheckmateException), UNEXPECTED_ERROR, '')

#TODO: full search, fix module reference all below here!!
@task
@statsd.collect
def create_environment(name, service_name, path=None, private_key=None,
                       public_key_ssh=None, secret_key=None, source_repo=None,
                       provider='chef-solo'):
    '''Create a knife-solo environment

    The environment is a directory structure that is self-contained and
    seperate from other environments. It is used by this provider to run knife
    solo commands.

    :param name: the name of the environment. This will be the directory name.
    :param path: an override to the root path where to create this environment
    :param private_key: PEM-formatted private key
    :param public_key_ssh: SSH-formatted public key
    :param secret_key: used for data bag encryption
    :param source_repo: provides cookbook repository in valid git syntax
    '''
    utils.match_celery_logging(LOG)

    #TODO: add context
    if utils.is_simulation(name):
        return {
            'environment': '/var/tmp/%s/' % name,
            'kitchen': '/var/tmp/%s/kitchen' % name,
            'private_key_path': '/var/tmp/%s/private.pem' % name,
            'public_key_path': '/var/tmp/%s/checkmate.pub' % name,
        }

    def on_failure(exc, task_id, args, kwargs, einfo):
        '''Handle task failure.'''
        if kwargs and kwargs.get('provider'):
            update_all_provider_resources.delay(kwargs.get('provider'),
                                                args[0],
                                                'ERROR',
                                                message=('Error creating chef '
                                                         'environment: %s'
                                                         % exc.args[0]))

    create_environment.on_failure = on_failure

    # Get path
    root = _get_root_environments_path(name, path)
    fullpath = os.path.join(root, name)

    # Create environment
    try:
        os.mkdir(fullpath, 0770)
        LOG.debug("Created environment directory: %s", fullpath)
    except OSError as ose:
        if ose.errno == errno.EEXIST:
            LOG.warn("Environment directory %s already exists", fullpath,
                     exc_info=True)
        else:
            msg = "Could not create environment %s", fullpath
            raise CheckmateUserException(msg, utils.get_class_name(
                CheckmateException), UNEXPECTED_ERROR, '')

    results = {"environment": fullpath}

    key_data = _create_environment_keys(name, fullpath,
                                        private_key=private_key,
                                        public_key_ssh=public_key_ssh)

    # Kitchen is created in a /kitchen subfolder since it gets completely
    # rsynced to hosts. We don't want the whole environment rsynced
    kitchen_data = _create_kitchen(name, service_name, fullpath,
                                   secret_key=secret_key,
                                   source_repo=source_repo)
    kitchen_path = os.path.join(fullpath, service_name)

    # Copy environment public key to kitchen certs folder
    public_key_path = os.path.join(fullpath, 'checkmate.pub')
    kitchen_key_path = os.path.join(kitchen_path, 'certificates',
                                    'checkmate-environment.pub')
    shutil.copy(public_key_path, kitchen_key_path)
    LOG.debug("Wrote environment public key to kitchen: %s", kitchen_key_path)

    if source_repo:
        # if Berksfile exists, run berks to pull in cookbooks
        if os.path.exists(os.path.join(kitchen_path, 'Berksfile')):
            _ensure_berkshelf_environment()
            _run_ruby_command(name, kitchen_path, 'berks', ['install',
                              '--path',
                              os.path.join(kitchen_path, 'cookbooks')],
                              lock=True)
            LOG.debug("Ran 'berks install' in: %s", kitchen_path)
        # If Cheffile exists, run librarian-chef to pull in cookbooks
        elif os.path.exists(os.path.join(kitchen_path, 'Cheffile')):
            _run_ruby_command(name, kitchen_path, 'librarian-chef',
                              ['install'], lock=True)
            LOG.debug("Ran 'librarian-chef install' in: %s", kitchen_path)
    else:
        error_message = "Source repo not supplied and is required"
        raise CheckmateUserException(error_message, utils.get_class_name(
            CheckmateException), BLUEPRINT_ERROR, '')

    results.update(kitchen_data)
    results.update(key_data)
    LOG.debug("create_environment returning: %s", results)
    return results


@task(max_retries=3, soft_time_limit=600)
@statsd.collect
def register_node(host, environment, resource, path=None, password=None,
                  omnibus_version=None, attributes=None, identity_file=None,
                  kitchen_name='kitchen'):
    '''Register a node in Chef.

    Using 'knife prepare' we will:
    - update apt caches on Ubuntu by default (which bootstrap does not do)
    - install chef on the client
    - register the node by creating as .json file for it in /nodes/

    Note: Maintaining same 'register_node' name as chefserver.py

    :param host: the public IP of the host (that's how knife solo tracks the
        nodes)
    :param environment: the ID of the environment/deployment
    :param resource: dict of resource information
    :param path: an optional override for path to the environment root
    :param password: the node's password
    :param omnibus_version: override for knife bootstrap (default=latest)
    :param attributes: attributes to set on node (dict)
    :param identity_file: private key file to use to connect to the node
    '''
    utils.match_celery_logging(LOG)

    #TODO: add context
    if utils.is_simulation(environment):
        res = {}
        host_results = {}
        host_results['status'] = "CONFIGURE"
        host_key = 'instance:%s' % resource['hosted_on']
        host_results = {host_key: host_results}
        res.update(host_results)

        # Update status of current resource to BUILD
        results = {}
        results['status'] = "BUILD"
        instance_key = 'instance:%s' % resource['index']
        results = {instance_key: results}
        res.update(results)

        resource_postback.delay(environment, res)
        return

    def on_failure(exc, task_id, args, kwargs, einfo):
        '''Handle task failure.'''
        if args and len(args) >= 3:
            resource = args[2]
            dep_id = args[1]
            host = args[0]
            if resource:
                k = "instance:%s" % resource.get('index')
                host_k = "instance:%s" % resource.get('hosted_on')
                ret = {}
                ret.update({
                    k: {
                        'status': 'ERROR',
                        'error-message': (
                            'Error registering host %s: %s' %
                            (host, exc)
                        )
                    }
                })
                if host_k:
                    ret.update({
                        host_k: {
                            'status': 'ERROR',
                            'error-message': (
                                'Error installing software resource %s' %
                                resource.get('index')
                            )
                        }
                    })
                resource_postback.delay(dep_id, ret)
        else:
            LOG.warn("Error callback for cook task %s did not get appropriate"
                     " args", task_id)

    register_node.on_failure = on_failure

    # Server provider updates status to CONFIGURE, but sometimes the server is
    # configured twice, so we need to do this update anyway just to be safe
    # Update status of host resource to CONFIGURE
    res = {}
    host_results = {}
    host_results['status'] = "CONFIGURE"
    host_key = 'instance:%s' % resource['hosted_on']
    host_results = {host_key: host_results}
    res.update(host_results)

    # Update status of current resource to BUILD
    results = {}
    results['status'] = "BUILD"
    instance_key = 'instance:%s' % resource['index']
    results = {instance_key: results}
    res.update(results)

    resource_postback.delay(environment, res)

    results = {}

    # Get path
    root = _get_root_environments_path(environment, path)
    kitchen_path = os.path.join(root, environment, kitchen_name)
    results = {}
    if not os.path.exists(kitchen_path):
        message = "Kitchen path %s does not exist!" % kitchen_path
        raise CheckmateUserException(message, utils.get_class_name(
            CheckmateException), UNEXPECTED_ERROR, '')

    # Rsync problem with creating path (missing -p so adding it ourselves) and
    # doing this before the complex prepare work
    try:
        ssh.remote_execute(host, "mkdir -p %s" % kitchen_path, 'root',
                           password=password, identity_file=identity_file)
    except SoftTimeLimitExceeded:
        msg = "Timeout trying to ssh to %s" % host
        LOG.info("%s in deployment %s", msg, environment)
        raise CheckmateUserException(msg, utils.get_class_name(
            CheckmateException), UNEXPECTED_ERROR, '')

    # Calculate node path and check for prexistance
    node_path = os.path.join(kitchen_path, 'nodes', '%s.json' % host)
    if os.path.exists(node_path):
        LOG.info("Node is already registered: %s", node_path)
    else:
        # Build and execute command 'knife prepare' command
        params = ['knife', 'solo', 'prepare', 'root@%s' % host,
                  '-c', os.path.join(kitchen_path, 'solo.rb')]
        if password:
            params.extend(['-P', password])
        if omnibus_version:
            params.extend(['--omnibus-version', omnibus_version])
        if identity_file:
            params.extend(['-i', identity_file])
        try:
            _run_kitchen_command(environment, kitchen_path, params)
            LOG.info("Knife prepare succeeded for %s in %s", host, environment)
        except SoftTimeLimitExceeded:
            msg = "Timeout trying to ssh to %s" % host
            LOG.info("%s in deployment %s", msg, environment)
            raise CheckmateUserException(msg, utils.get_class_name(
                CheckmateException), UNEXPECTED_ERROR, '')
        except (CalledProcessError, CheckmateCalledProcessError) as exc:
            LOG.warn("Knife prepare failed for %s. Retrying.", host)
            register_node.retry(exc=exc)
        except StandardError as exc:
            LOG.error("Knife prepare failed with an unhandled error '%s' for "
                      "%s.", exc, host)
            raise exc

    if attributes:
        lock = threading.Lock()
        lock.acquire()
        try:
            node = {'run_list': []}  # default
            with file(node_path, 'r') as node_file_r:
                node = json.load(node_file_r)
            node.update(attributes)
            with file(node_path, 'w') as node_file_w:
                json.dump(node, node_file_w)
            LOG.info("Node attributes written in %s", node_path, extra=dict(
                     data=node))
        except StandardError, exc:
            raise exc
        finally:
            lock.release()


@task(countdown=20, max_retries=3)
@statsd.collect
def manage_role(name, environment, resource, path=None, desc=None,
                run_list=None, default_attributes=None,
                override_attributes=None, env_run_lists=None,
                kitchen_name='kitchen'):
    '''Write/Update role.'''
    utils.match_celery_logging(LOG)

    #TODO: add context
    if utils.is_simulation(environment):
        return

    results = {}

    root = _get_root_environments_path(environment, path)
    kitchen_path = os.path.join(root, environment, kitchen_name)
    if not os.path.exists(kitchen_path):
        manage_role.retry(exc=CheckmateException("Environment does not exist: "
                                                 "%s" % kitchen_path))
    the_ruby = os.path.join(kitchen_path, 'roles', '%s.rb' % name)
    if os.path.exists(the_ruby):
        msg = ("Encountered a chef role in Ruby. Only JSON "
               "roles can be manipulated by Checkmate: %s" % the_ruby)
        results['status'] = "ERROR"
        results['error-message'] = msg
        instance_key = 'instance:%s' % resource['index']
        results = {instance_key: results}
        resource_postback.delay(environment, results)
        raise CheckmateUserException(msg, utils.get_class_name(
            CheckmateException), UNEXPECTED_ERROR, '')

    role_path = os.path.join(kitchen_path, 'roles', '%s.json' % name)

    if os.path.exists(role_path):
        with file(role_path, 'r') as role_file_r:
            role = json.load(role_file_r)
        if run_list is not None:
            role['run_list'] = run_list
        if default_attributes is not None:
            role['default_attributes'] = default_attributes
        if override_attributes is not None:
            role['override_attributes'] = override_attributes
        if env_run_lists is not None:
            role['env_run_lists'] = env_run_lists
    else:
        role = {
            "name": name,
            "chef_type": "role",
            "json_class": "Chef::Role",
            "default_attributes": default_attributes or {},
            "description": desc,
            "run_list": run_list or [],
            "override_attributes": override_attributes or {},
            "env_run_lists": env_run_lists or {}
        }

    LOG.debug("Writing role '%s' to %s", name, role_path)
    with file(role_path, 'w') as role_file_w:
        json.dump(role, role_file_w)
