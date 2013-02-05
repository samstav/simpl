from checkmate import utils
from checkmate.exceptions import CheckmateException, CheckmateCalledProcessError
from checkmate.ssh import execute as ssh_execute
from celery import task  # @UnresolvedImport
from subprocess import (CalledProcessError, check_output, Popen, PIPE)
from collections import deque
from Crypto.PublicKey import RSA
from Crypto.Random import atfork
import json
import logging
import os
import threading
import errno
import sys
import git
import shutil
import urlparse
from git.exc import GitCommandError

LOG = logging.getLogger(__name__)

CHECKMATE_CHEF_REPO = None


def register_scheme(scheme):
    '''
    Use this to register a new scheme with urlparse and have it be parsed
    in the same way as http is parsed
    '''
    for method in filter(lambda s: s.startswith('uses_'), dir(urlparse)):
        getattr(urlparse, method).append(scheme)

register_scheme('git')  # without this, urlparse won't handle git:// correctly


def _get_repo_path():
    """Find the master repo path for chef cookbooks"""
    global CHECKMATE_CHEF_REPO
    if not CHECKMATE_CHEF_REPO:
        CHECKMATE_CHEF_REPO = os.environ.get('CHECKMATE_CHEF_REPO')
        if not CHECKMATE_CHEF_REPO:
            CHECKMATE_CHEF_REPO = "/var/local/checkmate/chef-stockton"
            LOG.warning("CHECKMATE_CHEF_REPO variable not set. Defaulting to "
                        "%s" % CHECKMATE_CHEF_REPO)
            if not os.path.exists(CHECKMATE_CHEF_REPO):
                git.Repo.clone_from('git://github.rackspace.com/checkmate/'
                        'chef-stockton.git', CHECKMATE_CHEF_REPO)
                LOG.info("Cloned chef-stockton to %s" % CHECKMATE_CHEF_REPO)
    return CHECKMATE_CHEF_REPO


def _get_root_environments_path(path=None):
    """Build the path using provided inputs and using any environment variables
    or configuration settings"""
    root = path or os.environ.get("CHECKMATE_CHEF_LOCAL_PATH",
            "/var/local/checkmate/deployments")
    if not os.path.exists(root):
        raise CheckmateException("Invalid root path: %s" % root)
    return root


def check_all_output(params):
    """Similar to subprocess check_output, but returns all output in error if
    an error is raised.

    We use this for processing Knife output where the details of the error are
    piped to stdout and the actual error does not have everything we need"""
    ON_POSIX = 'posix' in sys.builtin_module_names

    def start_thread(func, *args):
        t = threading.Thread(target=func, args=args)
        t.daemon = True
        t.start()
        return t

    def consume(infile, output, errors):
        for line in iter(infile.readline, ''):
            output(line)
            if 'FATAL' in line:
                errors(line)
        infile.close()

    p = Popen(params, stdout=PIPE, stderr=PIPE, bufsize=1, close_fds=ON_POSIX)

    # preserve last N lines of stdout and stderr
    N = 100
    queue = deque(maxlen=N)  # will capture output
    errors = deque(maxlen=N)  # will capture Knife errors (contain 'FATAL')
    threads = [start_thread(consume, *args)
                for args in (p.stdout, queue.append, errors.append),
                (p.stderr, queue.append, errors.append)]
    for t in threads:
        t.join()  # wait for IO completion

    retcode = p.wait()

    if retcode == 0:
        return '%s%s' % (''.join(errors), ''.join(queue))
    else:
        # Raise CalledProcessError, but include the Knife-specifc errors
        raise CheckmateCalledProcessError(retcode, ' '.join(params),
                output='\n'.join(queue), error_info='\n'.join(errors))


def _run_ruby_command(path, command, params, lock=True):
    """Runs a knife-like command (ex. librarian-chef).

    Since knife-ike command errors are returned to stderr, we need to capture
    stderr and check for errors.

    That needs to be run in a kitchen, so we move curdir and need to make sure
    we stay there, so I added some synchronization code while that takes place
    However, if code calls in that already has a lock, the optional lock param
    can be set to false so thise code does not lock.
    :param version_param: the parameter used to get the command's version. This
            is used to check if the program is installed.
    """
    params.insert(0, command)
    LOG.debug("Running: '%s' in path '%s'" % (' '.join(params), path))
    if lock:
        path_lock = threading.Lock()
        path_lock.acquire()
        try:
            if path:
                os.chdir(path)
            result = check_all_output(params)  # check_output(params)
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                # Check if command is installed
                output = None
                try:
                    output = check_output(['which', command])
                except CalledProcessError:
                    pass
                if not output:
                    raise CheckmateException("'%s' is not installed or not "
                                             "accessible on the server" %
                                             command)
            raise exc
        except CalledProcessError, exc:
            #retry and pass ex
            # CalledProcessError cannot be serialized using Pickle, so raising
            # it would fail in celery; we wrap the exception in something
            # Pickle-able.
            raise CheckmateCalledProcessError(exc.returncode, exc.cmd,
                                              output=exc.output)
        finally:
            path_lock.release()
    else:
        if path:
            os.chdir(path)
        result = check_all_output(params)
    LOG.debug(result)
    # Knife-like commands succeed even if there is an error. This code tries to
    # parse the output to return a useful error
    fatal = []
    last_fatal = ''
    for line in result.split('\n'):
        if 'FATAL:' in line:
            fatal.append(line)
            last_fatal = line
    if fatal:
        command = ' '.join(params)
        if 'Chef::Exceptions::' in last_fatal:
            # Get the string after Chef::Exceptions::
            error = last_fatal.split('::')[-1]
            if error:
                raise CheckmateCalledProcessError(1, command,
                        output="Chef/Knife error encountered: %s" % error)
        output = '\n'.join(fatal)
        raise CheckmateCalledProcessError(1, command, output=output)

    return result


def _run_kitchen_command(kitchen_path, params, lock=True):
    """Runs the 'knife xxx' command.

    This also needs to handle knife command errors, which are returned to
    stderr.

    That needs to be run in a kitchen, so we move curdir and need to make sure
    we stay there, so I added some synchronization code while that takes place
    However, if code calls in that already has a lock, the optional lock param
    can be set to false so thise code does not lock
    """
    LOG.debug("Running: '%s' in path '%s'" % (' '.join(params), kitchen_path))
    if '-c' not in params:
        LOG.warning("Knife command called without a '-c' flag. The '-c' flag "
                  "is a strong safeguard in case knife runs in the wrong "
                  "directory. Consider adding it and pointing to solo.rb")
        config_file = os.path.join(kitchen_path, 'solo.rb')
        if os.path.exists(config_file):
            LOG.debug("Defaulting to config file '%s'" % config_file)
            params.extend(['-c', config_file])
    result = _run_ruby_command(kitchen_path, params[0], params[1:], lock=lock)

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
                raise CheckmateCalledProcessError(1, ' '.join(params),
                        output="Knife error encountered: %s" % error)
            # Don't raise on all errors. They don't all mean failure!
    return result


def _create_environment_keys(environment_path, private_key=None,
        public_key_ssh=None):
    """Put keys in an existing environment

    If none are provided, a new set of public/private keys are created
    """
    # Create private key
    private_key_path = os.path.join(environment_path, 'private.pem')
    if os.path.exists(private_key_path):
        # Already exists.
        if private_key:
            with file(private_key_path, 'r') as f:
                data = f.read()
            if data != private_key:
                raise CheckmateException("A private key already exists in "
                        "environment %s and does not match the value provided "
                        % environment_path)
    else:
        if private_key:
            with file(private_key_path, 'w') as f:
                f.write(private_key)
            LOG.debug("Wrote environment private key: %s" % private_key_path)
        else:
            params = ['openssl', 'genrsa', '-out', private_key_path, '2048']
            result = check_output(params)
            LOG.debug(result)
            LOG.debug("Generated environment private key: %s" %
                      private_key_path)

    # Secure private key
    os.chmod(private_key_path, 0600)
    LOG.debug("Private cert permissions set: chmod 0600 %s" %
            private_key_path)

    # Get or Generate public key
    public_key_path = os.path.join(environment_path, 'checkmate.pub')
    if os.path.exists(public_key_path):
        LOG.debug("Public key exists. Retrieving it from %s" % public_key_path)
        with file(public_key_path, 'r') as f:
            public_key_ssh = f.read()
    else:
        if not public_key_ssh:
            params = ['ssh-keygen', '-y', '-f', private_key_path]
            public_key_ssh = check_output(params)
            LOG.debug("Generated environment public key: %s" % public_key_path)
        # Write it to environment
        with file(public_key_path, 'w') as f:
            f.write(public_key_ssh)
        LOG.debug("Wrote environment public key: %s" % public_key_path)
    return dict(public_key_ssh=public_key_ssh, public_key_path=public_key_path,
            private_key_path=private_key_path)


def _write_knife_config_file(kitchen_path):
    """Writes a solo.rb config file and links a knife.rb file too"""
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
    LOG.debug("Created solo file: %s" % solo_file)
    return (solo_file, secret_key_path)


def _init_repo(path, source_repo=None):
    """

    Initialize a git repo.

    If a remote is supplied, we pull it in.

    If the remote has a reference appended as a fragment, we fetch that and
    check it out as a detached head.

    """
    if not os.path.exists(path):
        raise CheckmateException("Invalid repo path: %s" % path)

    # Init git repo
    repo = git.Repo.init(path)

    if source_repo:  # Pull remote if supplied
        source_repo, ref = urlparse.urldefrag(source_repo)
        LOG.debug("Fetching ref %s from %s" % (ref or 'master', source_repo))
        remotes = [r for r in repo.remotes
                     if r.config_reader.get('url') == source_repo]
        if remotes:
            remote = remotes[0]
        else:
            #FIXME: there's a gap here. We don't check if origin exists.
            remote = repo.create_remote('origin', source_repo)
        try:
            remote.fetch(refspec=ref or 'master')
        except GitCommandError as gce:
            LOG.error("Error fetching source repo: %s" % str(gce))
            raise gce
        git_binary = git.Git(path)
        git_binary.checkout('FETCH_HEAD')
        LOG.debug("Fetched '%s' ref '%s' into repo: %s" % (source_repo,
                                                          ref or 'master',
                                                          path))
    else:
        # Make path a git repo
        file_path = os.path.join(path, '.gitignore')
        with file(file_path, 'w') as f:
            f.write("#Checkmate Created Repo")
        index = repo.index
        index.add(['.gitignore'])
        index.commit("Initial commit")
        LOG.debug("Initialized blank repo: %s" % path)


def _create_kitchen(name, path, secret_key=None):
    """Creates a new knife-solo kitchen in path

    :param name: the name of the kitchen
    :param path: where to create the kitchen
    :param secret_key: PEM-formatted private key for data bag encryption
    """
    if not os.path.exists(path):
        raise CheckmateException("Invalid path: %s" % path)

    kitchen_path = os.path.join(path, name)
    if not os.path.exists(kitchen_path):
        os.mkdir(kitchen_path, 0770)
        LOG.debug("Created kitchen directory: %s" % kitchen_path)
    else:
        LOG.debug("Kitchen directory exists: %s" % kitchen_path)

    nodes_path = os.path.join(kitchen_path, 'nodes')
    if os.path.exists(nodes_path):
        if any((f.endswith('.json') for f in os.listdir(nodes_path))):
            raise CheckmateException("Kitchen already exists and seems to "
                    "have nodes defined in it: %s" % nodes_path)
    else:
        # we don't pass the config file here becasuse we're creating the
        # kitchen for the first time and knife will overwrite our config file
        params = ['knife', 'kitchen', '.']
        _run_kitchen_command(kitchen_path, params)

    solo_file, secret_key_path = _write_knife_config_file(kitchen_path)

    # Copy bootstrap.json to the kitchen
    repo_path = _get_repo_path()
    bootstrap_path = os.path.join(repo_path, 'bootstrap.json')
    if not os.path.exists(bootstrap_path):
        raise CheckmateException("Invalid master repo. {} not found"
                                 .format(bootstrap_path))
    shutil.copy(bootstrap_path, os.path.join(kitchen_path, 'bootstrap.json'))

    # Create certificates folder
    certs_path = os.path.join(kitchen_path, 'certificates')
    if os.path.exists(certs_path):
        LOG.debug("Certs directory exists: %s" % certs_path)
    else:
        os.mkdir(certs_path, 0770)
        LOG.debug("Created certs directory: %s" % certs_path)

    # Store (generate if necessary) the secrets file
    if os.path.exists(secret_key_path):
        if secret_key:
            with file(secret_key_path, 'r') as f:
                data = f.read(secret_key)
            if data != secret_key:
                raise CheckmateException("Kitchen secrets key file '%s' "
                        "already exists and does not match the provided value"
                        % secret_key_path)
        LOG.debug("Stored secrets file exists: %s" % secret_key_path)
    else:
        if not secret_key:
            # celery runs os.fork(). We need to reset the random number
            # generator before generating a key. See atfork.__doc__
            atfork()
            key = RSA.generate(2048)
            secret_key = key.exportKey('PEM')
            LOG.debug("Generated secrets private key")
        with file(secret_key_path, 'w') as f:
            f.write(secret_key)
        LOG.debug("Stored secrets file: %s" % secret_key_path)

    # Knife defaults to knife.rb, but knife-solo looks for solo.rb, so we link
    # both files so that knife and knife-solo commands will work and anyone
    # editing one will also change the other
    knife_file = os.path.join(path, name, 'knife.rb')
    if os.path.exists(knife_file):
        LOG.debug("Knife.rb already exists: %s" % knife_file)
    else:
        os.link(solo_file, knife_file)
        LOG.debug("Linked knife.rb: %s" % knife_file)

    LOG.debug("Finished creating kitchen: %s" % kitchen_path)
    return {"kitchen": kitchen_path}


@task
def write_databag(environment, bagname, itemname, contents,
        path=None, secret_file=None, merge=True, kitchen_name='kitchen'):
    """Updates a data_bag or encrypted_data_bag

    :param environment: the ID of the environment
    :param bagname: the name of the databag (in solo, this ends up being a
            directory)
    :param item: the name of the item (in solo this ends up being a .json file)
    :param contents: this is a dict of attributes to write in to the databag
    :param path: optional override to the default path where environments live
    :param secret_file: the path to a certificate used to encrypt a data_bag
    :param merge: if True, the data will be merged in. If not, it will be
            completely overwritten
    :param kitchen_name: Optional name of kitchen to write to.  default: kitchen

    """
    utils.match_celery_logging(LOG)
    root = _get_root_environments_path(path)
    kitchen_path = os.path.join(root, environment, kitchen_name)
    databags_root = os.path.join(kitchen_path, 'data_bags')
    if not os.path.exists(databags_root):
        raise CheckmateException("Data bags path does not exist: %s" %
                databags_root)

    # Check if the bag already exists (create it if not)
    config_file = os.path.join(kitchen_path, 'solo.rb')
    params = ['knife', 'solo', 'data', 'bag', 'list', '-F', 'json',
              '-c', config_file]
    data_bags = _run_kitchen_command(kitchen_path, params)
    if data_bags:
        data_bags = json.loads(data_bags)
    if bagname not in data_bags:
        merge = False  # Nothing to merge if it is new!
        _run_kitchen_command(kitchen_path, ['knife', 'solo', 'data',
                                   'bag', 'create', bagname, '-c',
                                    config_file])
        LOG.debug("Created data bag '%s' in '%s'" % (bagname, databags_root))

    # Check if the item already exists (create it if not)
    params = ['knife', 'solo', 'data', 'bag', 'show', bagname, '-F', 'json',
              '-c', config_file]
    existing_contents = _run_kitchen_command(kitchen_path, params)
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
            data = _run_kitchen_command(kitchen_path, params)
            existing = json.loads(data)
            contents = utils.merge_dictionary(existing, contents)
            if isinstance(contents, dict):
                contents = json.dumps(contents)
            params = ['knife', 'solo', 'data', 'bag', 'create', bagname,
                      itemname, '-c', config_file, '-d', '--json', contents]
            if secret_file:
                params.extend(['--secret-file', secret_file])
            result = _run_kitchen_command(kitchen_path, params,
                                                lock=False)
        except CalledProcessError, exc:
            # Reraise pickleable exception
            raise CheckmateCalledProcessError(exc.returncode, exc.cmd,
                    output=exc.output)
        finally:
            lock.release()
        LOG.debug(result)
    else:
        if contents:
            if 'id' not in contents:
                contents['id'] = itemname
            elif contents['id'] != itemname:
                raise CheckmateException("The value of the 'id' field in a "
                        "databag item is reserved by Chef and must be set to "
                        "the name of the databag item. Checkmate will set "
                        "this for you if it is missing, but the data you "
                        "supplied included an ID that did not match the "
                        "databag item name. The ID was '%s' and the databag "
                        "item name was '%s'" % (contents['id'], itemname))
            if isinstance(contents, dict):
                contents = json.dumps(contents)
            params = ['knife', 'solo', 'data', 'bag', 'create', bagname,
                       itemname, '-d', '-c', config_file, '--json', contents]
            if secret_file:
                params.extend(['--secret-file', secret_file])
            result = _run_kitchen_command(kitchen_path, params)
            LOG.debug(result)
        else:
            LOG.warning("write_databag was called with no contents")


@task(countdown=20, max_retries=3)
def cook(host, environment, recipes=None, roles=None, path=None,
         username='root', password=None, identity_file=None, port=22,
         attributes=None, kitchen_name='kitchen'):
    """Apply recipes/roles to a server"""
    utils.match_celery_logging(LOG)
    root = _get_root_environments_path(path)
    kitchen_path = os.path.join(root, environment, kitchen_name)
    if not os.path.exists(kitchen_path):
        raise CheckmateException("Environment kitchen does not exist: %s" %
                kitchen_path)
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
            with file(node_path, 'r') as f:
                node = json.load(f)
            if run_list:
                for entry in run_list:
                    if entry not in node['run_list']:
                        node['run_list'].append(entry)
                        add_list.append(entry)
            if attributes:
                utils.merge_dictionary(node, attributes)
            if add_list or attributes:
                with file(node_path, 'w') as f:
                    json.dump(node, f)
        finally:
            lock.release()
        if add_list:
            LOG.debug("Added to %s: %s" % (node_path, add_list))
        else:
            LOG.debug("All run_list already exists in %s: %s" % (node_path,
                      run_list))
        if attributes:
            LOG.debug("Wrote attributes to %s" % node_path,
                      extra={'data': attributes})
    else:
        LOG.debug("No recipes or roles to add and no attribute changes. Will "
                  "just run 'knife cook' for %s using bootstrap.json" %
                  node_path)

    # Build and run command
    if not username:
        username = 'root'
    params = ['knife', 'cook', '%s@%s' % (username, host),
              '-c', os.path.join(kitchen_path, 'solo.rb')]
    if not (run_list or attributes):
        params.extend(['bootstrap.json'])
    if identity_file:
        params.extend(['-i', identity_file])
    if password:
        params.extend(['-P', password])
    if port:
        params.extend(['-p', str(port)])
    _run_kitchen_command(kitchen_path, params)


def download_cookbooks(environment, service_name, path=None, cookbooks=None,
        source=None, use_site=False):
    """Download cookbooks from a remote repo
    :param environment: the name of the kitchen/environment environment.
        It should have cookbooks and site-cookbooks subfolders
    :param path: points to the root of environments.
        It should have cookbooks and site-cookbooks subfolders
    :param cookbooks: the names of the cookbooks to download (blank=all)
    :param source: the source repos (a github URL)
    :param use_site: use site-cookbooks instead of cookbooks
    :returns: count of cookbooks copied"""
    utils.match_celery_logging(LOG)
    # Until we figure out a better solution, I'm assuming the chef-stockton
    # repo is cloned as a subfolder under the provider (and cloning it if
    # not) and we copy the cookbooks from there

    # Get path
    root = _get_root_environments_path(path)
    fullpath = os.path.join(root, environment)
    if not os.path.exists(fullpath):
        raise CheckmateException("Environment does not exist: %s" % fullpath)
    kitchen_path = os.path.join(fullpath, service_name)
    if not os.path.exists(kitchen_path):
        raise CheckmateException("Kitchen does not exist: %s" % kitchen_path)

    # Find/get cookbook source
    repo_path = _get_repo_path()

    if use_site:
        cookbook_subdir = 'site-cookbooks'
    else:
        cookbook_subdir = 'cookbooks'

    # Check that cookbooks requested exist
    if cookbooks:
        for cookbook in cookbooks:
            if not os.path.exists(os.path.join(repo_path, cookbook_subdir,
                    cookbook)):
                raise CheckmateException("Cookbook '%s' not available in repo:"
                        " %s" % (cookbook, repo_path))
    else:
        # If none specificed, assume all
        cookbooks = [p for p in os.listdir(os.path.join(repo_path,
                cookbook_subdir)) if os.path.isdir(os.path.join(repo_path,
                cookbook_subdir, p))]

    # Copy the cookbooks over
    count = 0
    for cookbook in cookbooks:
        target = os.path.join(kitchen_path, cookbook_subdir, cookbook)
        if not os.path.exists(target):
            LOG.debug("Copying cookbook '%s' to %s" % (cookbook, repo_path))
            shutil.copytree(os.path.join(repo_path, cookbook_subdir, cookbook),
                    target)
            count += 1
    return count


def download_roles(environment, service_name, path=None, roles=None,
                   source=None):
    """Download roles from a remote repo
    :param environment: the name of the kitchen/environment environment.
        It should have a roles subfolder.
    :param path: points to the root of environments.
        It should have a roles subfolders
    :param roles: the names of the roles to download (blank=all)
    :param source: the source repos (a github URL)
    :returns: count of roles copied"""
    utils.match_celery_logging(LOG)
    # Until we figure out a better solution, I'm assuming the chef-stockton
    # repo is cloned as a subfolder under python-stockton (and cloning it if
    # not) and we copy the roles from there

    # Get path
    root = _get_root_environments_path(path)
    fullpath = os.path.join(root, environment)
    if not os.path.exists(fullpath):
        raise CheckmateException("Environment does not exist: %s" % fullpath)
    kitchen_path = os.path.join(fullpath, service_name)
    if not os.path.exists(kitchen_path):
        raise CheckmateException("Kitchen does not exist: %s" % kitchen_path)

    # Find/get cookbook source
    repo_path = _get_repo_path()

    if not os.path.exists(repo_path):
        rax_repo = 'git://github.rackspace.com/ManagedCloud/chef-stockton.git'
        git.Repo.clone_from(rax_repo, repo_path)
        LOG.info("Cloned chef-stockton from %s to %s" % (rax_repo, repo_path))
    else:
        LOG.debug("Getting roles from %s" % repo_path)

    # Check that roles requested exist
    if roles:
        for role in roles:
            if not os.path.exists(os.path.join(repo_path, 'roles',
                    role)):
                raise CheckmateException("Role '%s' not available in repo: "
                        "%s" % (role, repo_path))
    else:
        # If none specificed, assume all
        roles = [p for p in os.listdir(os.path.join(repo_path, 'roles'))]

    # Copy the roles over
    count = 0
    for role in roles:
        target = os.path.join(kitchen_path, 'roles', role)
        if not os.path.exists(target):
            LOG.debug("Copying role '%s' to %s" % (role, repo_path))
            shutil.copy(os.path.join(repo_path, 'roles', role), target)
            count += 1
    return count


#TODO: full search, fix module reference all below here!!
@task
def create_environment(name, service_name, path=None, private_key=None,
                       public_key_ssh=None, secret_key=None, source_repo=None):
    """Create a knife-solo environment

    The environment is a directory structure that is self-contained and
    seperate from other environments. It is used by this provider to run knife
    solo commands.

    :param name: the name of the environment. This will be the directory name.
    :param path: an override to the root path where to create this environment
    :param private_key: PEM-formatted private key
    :param public_key_ssh: SSH-formatted public key
    :param secret_key: used for data bag encryption
    :param source_repo: provides cookbook repository in valid git syntax
    """
    utils.match_celery_logging(LOG)
    # Get path
    root = _get_root_environments_path(path)
    fullpath = os.path.join(root, name)

    # Create environment
    try:
        os.mkdir(fullpath, 0770)
        LOG.debug("Created environment directory: %s" % fullpath)
    except OSError as ose:
        if ose.errno == errno.EEXIST:
            LOG.warn("Environment directory %s already exists", fullpath,
                      exc_info=True)
        else:
            raise CheckmateException(
                "Could not create environment %s" % fullpath, ose)

    results = {"environment": fullpath}

    key_data = _create_environment_keys(fullpath, private_key=private_key,
            public_key_ssh=public_key_ssh)

    # Kitchen is created in a /kitchen subfolder since it gets completely
    # rsynced to hosts. We don't want the whole environment rsynced
    kitchen_data = _create_kitchen(service_name, fullpath,
            secret_key=secret_key)
    kitchen_path = os.path.join(fullpath, service_name)

    # Copy environment public key to kitchen certs folder
    public_key_path = os.path.join(fullpath, 'checkmate.pub')
    kitchen_key_path = os.path.join(kitchen_path, 'certificates',
            'checkmate-environment.pub')
    shutil.copy(public_key_path, kitchen_key_path)
    LOG.debug("Wrote environment public key to kitchen: %s" % kitchen_key_path)

    if source_repo:
        _init_repo(kitchen_path, source_repo=source_repo)
        # If Cheffile exists, all librarian-chef to pull in cookbooks
        if os.path.exists(os.path.join(kitchen_path, 'Cheffile')):
            _run_ruby_command(kitchen_path, 'librarian-chef', ['install'],
                              lock=True)
            LOG.debug("Ran 'librarian-chef install' in: %s" % kitchen_path)
    else:
        _init_repo(os.path.join(kitchen_path, 'cookbooks'))
        # Keep for backwards compatibility, but source_repo should be provided
        # Temporary Hack: load all cookbooks and roles from chef-stockton
        # TODO: Undo this and use more git
        download_cookbooks(name, service_name, path=root)
        download_cookbooks(name, service_name, path=root, use_site=True)
        download_roles(name, service_name, path=root)

    results.update(kitchen_data)
    results.update(key_data)
    LOG.debug("create_environment returning: %s" % results)
    return results


@task
def register_node(host, environment, path=None, password=None,
        omnibus_version=None, attributes=None, identity_file=None,
        kitchen_name='kitchen'):
    """Register a node in Chef.

    Using 'knife prepare' we will:
    - update apt caches on Ubuntu by default (which bootstrap does not do)
    - install chef on the client
    - register the node by creating as .json file for it in /nodes/

    Note: Maintaining same 'register_node' name as chefserver.py

    :param host: the public IP of the host (that's how knife solo tracks the
        nodes)
    :param environment: the ID of the environment
    :param path: an optional override for path to the environment root
    :param password: the node's password
    :param omnibus_version: override for knife bootstrap (default=latest)
    :param attributes: attributes to set on node (dict)
    :param identity_file: private key file to use to connect to the node
    """
    utils.match_celery_logging(LOG)
    # Get path
    root = _get_root_environments_path(path)
    kitchen_path = os.path.join(root, environment, kitchen_name)
    if not os.path.exists(kitchen_path):
        raise CheckmateException("Environment kitchen does not exist: %s" %
                kitchen_path)

    # Rsync problem with creating path (missing -p so adding it ourselves) and
    # doing this before the complex prepare work
    ssh_execute(host, "mkdir -p %s" % kitchen_path, 'root', password=password,
            identity_file=identity_file)

    # Calculate node path and check for prexistance
    node_path = os.path.join(kitchen_path, 'nodes', '%s.json' % host)
    if os.path.exists(node_path):
        raise CheckmateException("Node seems to already be registered: %s" %
                node_path)

    # Build and execute command 'knife prepare' command
    params = ['knife', 'prepare', 'root@%s' % host,
              '-c', os.path.join(kitchen_path, 'solo.rb')]
    if password:
        params.extend(['-P', password])
    if omnibus_version:
        params.extend(['--omnibus-version', omnibus_version])
    if identity_file:
        params.extend(['-i', identity_file])
    _run_kitchen_command(kitchen_path, params)
    LOG.info("Knife prepare succeeded for %s" % host)

    if attributes:
        lock = threading.Lock()
        lock.acquire()
        try:
            node = {'run_list': []}  # default
            with file(node_path, 'r') as f:
                node = json.load(f)
            node.update(attributes)
            with file(node_path, 'w') as f:
                json.dump(node, f)
            LOG.info("Node attributes written in %s" % node_path, extra=dict(
                    data=node))
        except StandardError, exc:
            raise exc
        finally:
            lock.release()


@task(countdown=20, max_retries=3)
def manage_role(name, environment, path=None, desc=None,
        run_list=None, default_attributes=None, override_attributes=None,
        env_run_lists=None, kitchen_name='kitchen'):
    """Write/Update role"""
    utils.match_celery_logging(LOG)
    root = _get_root_environments_path(path)
    kitchen_path = os.path.join(root, environment, kitchen_name)
    if not os.path.exists(kitchen_path):
        manage_role.retry(exc=CheckmateException(
                             "Environment does not exist: %s" %
                             kitchen_path))
    the_ruby = os.path.join(kitchen_path, 'roles', '%s.rb' % name)
    if os.path.exists(the_ruby):
        raise CheckmateException("Encountered a chef role in Ruby. Only JSON "
                "roles can be manipulated by Checkmate: %s" % the_ruby)

    role_path = os.path.join(kitchen_path, 'roles', '%s.json' % name)

    if os.path.exists(role_path):
        with file(role_path, 'r') as f:
            role = json.load(f)
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

    LOG.debug("Writing role '%s' to %s" % (name, role_path))
    with file(role_path, 'w') as f:
        json.dump(role, f)
