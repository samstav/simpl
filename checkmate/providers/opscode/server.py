
import logging

from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.specs import Celery, Merge, Transform

from checkmate.providers import ProviderBase
from checkmate.workflows import wait_for
from checkmate.utils import match_celery_logging

LOG = logging.getLogger(__name__)


class Provider(ProviderBase):
    name = 'chef-server'
    vendor = 'opscode'

    """Implements a Chef Server configuration management provider"""
    def __init__(self, provider, key=None):
        ProviderBase.__init__(self, provider, key=key)
        self.prep_task = None

    def provides(self, resource_type=None, interface=None):
        return [dict(application='http'), dict(database='mysql')]

    def prep_environment(self, wfspec, deployment, context):
        create_environment = Celery(wfspec, 'Create Chef Environment',
                'checkmate.providers.opscode.server.manage_env',
                call_args=[Attrib('context'), deployment['id'],
                        'Checkmate Environment'],
                properties={'estimated_duration': 10})
        self.prep_task = create_environment
        return {'root': self.prep_task, 'final': self.prep_task}

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                wait_on=None):
        register_node_task = Celery(wfspec, 'Register Server:%s (%s)' % (key, resource['service']),
                        'checkmate.providers.opscode.server.register_node',
                        call_args=[Attrib('context'),
                               resource.get('dns-name'), ['wordpress-web']],
                        environment=deployment['id'],
                        defines=dict(resource=key, provider=self.key),
                        description="Register the "
                                "node in the Chef Server. Nothing is done "
                                "the node itself",
                        properties={'estimated_duration': 20})
        self.prep_task.connect(register_node_task)

        ssh_apt_get_task = Celery(wfspec, 'Apt-get Fix:%s (%s)' % (key, resource['service']),
                           'checkmate.ssh.execute',
                            call_args=[Attrib('ip'),
                                    "sudo apt-get update",
                                    'root'],
                            password=Attrib('password'),
                            identity_file=Attrib('private_key_path'),
                            properties={'estimated_duration': 100})
        # TODO: stop assuming only one wait_on=create_server_task
        wait_on[0].connect(ssh_apt_get_task)

        bootstrap_task = Celery(wfspec, 'Bootstrap Server:%s (%s)' % (key, resource['service']),
                           'checkmate.providers.opscode.server.bootstrap',
                            call_args=[Attrib('context'),
                                    resource.get('dns-name'), Attrib('ip')],
                            password=Attrib('password'),
                            identity_file=Attrib('private_key_path'),
                            run_roles=['build', 'wordpress-web'],
                            environment=deployment['id'],
                            properties={'estimated_duration': 90})
        wait_for(wfspec, bootstrap_task,
                [ssh_apt_get_task, register_node_task],
                name="Wait for Server Build:%s (%s)" % (key, resource['service']))
        return {'root': register_node_task, 'final': bootstrap_task}

    def add_connection_tasks(self, resource, key, relation, relation_key,
            wfspec, deployment):
        target = deployment['resources'][relation['target']]
        interface = relation['interface']

        if interface == 'mysql':
            #Take output from Create DB task and write it into
            # the 'override' dict to be available to future tasks

            db_final = self.find_resource_task(wfspec, relation['target'],
                    target['provider'], 'final')

            compile_override = Transform(wfspec, "Prepare Overrides",
                    transforms=[
                    "my_task.attributes['overrides']={'wordpress': {'db': "
                    "{'host': my_task.attributes['hostname'], "
                    "'database': my_task.attributes['context']['db_name'], "
                    "'user': my_task.attributes['context']['db_username'], "
                    "'password': my_task.attributes['context']"
                    "['db_password']}}}"],
                    description="Get all the variables "
                            "we need (like database name and password) and "
                            "compile them into JSON that we can set on the "
                            "role or environment",
                    defines=dict(relation=relation_key,
                                provider=self.key,
                                task_tags=None))
            db_final.connect(compile_override)

            set_overrides = Celery(wfspec,
                "Write Database Settings",
                'checkmate.providers.opscode.server.manage_env',
                call_args=[Attrib('context'), deployment['id']],
                    desc='Checkmate Environment',
                    override_attributes=Attrib('overrides'),
                description="Take the JSON prepared earlier and write "
                        "it into the environment overrides. It will "
                        "be used by the Chef recipe to connect to "
                        "the database",
                defines=dict(relation=relation_key,
                            resource=key,
                            provider=self.key,
                            task_tags=None),
                properties={'estimated_duration': 15})

            wait_on = [compile_override, self.prep_task]
            wait_for(wfspec, set_overrides, wait_on,
                    name="Wait on Environment and Settings:%s" % key)

            config_final = self.find_resource_task(wfspec, key, self.key,
                    'final')
            # Assuming input is join
            assert isinstance(config_final.inputs[0], Merge)
            set_overrides.connect(config_final.inputs[0])

        else:
            LOG.warning("Provider '%s' does not recognized connection "
                    "interface '%s'" % (self.key, interface),
                    defines=dict(relation=relation_key,
                                provider=self.key,
                                task_tags=None))


"""
  Celery tasks to manipulate Chef

    Set CHEF_PATH environment variable if you want to use a specific
    configuration instance. The knife.rb from that path will be used.
"""
import os
from subprocess import check_output, CalledProcessError

from celery.task import task
import chef


def create_role_recipe_string(roles=None, recipes=None):
    s = ''
    if roles is not None:
        for role in roles:
            s += 'role[%s], ' % role
    if recipes is not None:
        for recipe in recipes:
            s += 'recipe[%s], ' % recipe
    # remove the trailing space and comma
    return s[:-2]

""" Celery tasks """


@task
def register_node(deployment, name, runlist=None, attributes=None,
                             environment=None):
    match_celery_logging(LOG)
    try:
        api = chef.autoconfigure(
                base_path=os.environ.get('STOCKTON_CHEF_PATH'))
        n = chef.Node(name, api=api)
        if runlist is not None:
            n.run_list = runlist
        if attributes is not None:
            n.normal = attributes
        if environment is not None:
            n.chef_environment = environment
        n.save()
        LOG.debug(
            'Registered %s with Chef Server. Setting runlist to %s' % (
            name, runlist))
    except chef.ChefError, exc:
        LOG.debug(
            'Node registration failed. Chef Error: %s. Retrying.' % exc)
        register_node.retry(exc=exc)
    except Exception, exc:
        LOG.debug('Node registration failed. Error: %s. Retrying.' % exc)
        register_node.retry(exc=exc)


@task
def bootstrap(deployment, name, ip, username='root', password=None,
                         port=22, identity_file=None, run_roles=None,
                         run_recipes=None, distro='chef-full',
                         environment=None):
    match_celery_logging(LOG)
    LOG.debug('Bootstraping %s (%s:%d)' % (name, ip, port))
    run_roles_recipes = create_role_recipe_string(roles=run_roles,
                                                  recipes=run_recipes)
    params = ['knife', 'bootstrap', ip, '-x', username, '-N', name]
    if identity_file:
        params.extend(['-i', identity_file])
    if distro:
        params.extend(['-d', distro])
    if run_roles_recipes:
        params.extend(['-r', run_roles_recipes])
    if password:
        params.extend(['-P', password])
    if port:
        params.extend(['-p', str(port)])
    if environment:
        params.extend(['-E', environment])

    path = os.environ.get('CHECKMATE_CHEF_PATH')
    if path:
        if os.path.exists(os.path.join(path, 'knife.rb')):
            params.extend(['-c', os.path.join(path, 'knife.rb')])

    LOG.debug('Running: %s' % ' '.join(params))
    result = check_output(params)
    if 'FATAL' in result:
        errors = [line for line in result.split('/n') if 'FATAL' in line]
        LOG.debug("Bootstrap errors: %s" % '/n'.join(errors))
        raise CalledProcessError('/n'.join(errors), ' '.join(params))
    return True


@task
def manage_databag(deployment, bagname, itemname, contents):
    match_celery_logging(LOG)
    try:
        api = chef.autoconfigure(
                base_path=os.environ.get('CHECKMATE_CHEF_PATH'))
        bag = chef.DataBag(bagname, api=api)
        bag.save()
        item = chef.DataBagItem(bag, itemname)
        for key, value in contents.iteritems():
            item[key] = value
        item.save()
        LOG.debug(
            'Databag %s updated. Setting items to %s' % (
            bag, item))
    except chef.ChefError, exc:
        LOG.debug(
            'Databag management failed. Chef Error: %s. Retrying.' % exc)
        manage_databag.retry(exc=exc)
    except Exception, exc:
        LOG.debug('Databag management failed. Error: %s. Retrying.' % exc)
        manage_databag.retry(exc=exc)


@task
def manage_role(deployment, name, desc=None, run_list=None,
                default_attributes=None, override_attributes=None,
                env_run_lists=None):
    match_celery_logging(LOG)
    try:
        api = chef.autoconfigure(
                base_path=os.environ.get('CHECKMATE_CHEF_PATH'))
        r = chef.Role(name, api=api)
        if desc is not None:
            r.description = desc
        if run_list is not None:
            r.run_list = run_list
        if default_attributes is not None:
            r.default_attributes = default_attributes
        if override_attributes is not None:
            r.override_attributes = override_attributes
        if env_run_lists is not None:
            r.env_run_lists = env_run_lists
        r.save()
        LOG.debug("Role %s updated. runlist set to %s. Default attributes set "
                "to %s. Override attributes set to %s. Environment run lists "
                "set to %s." % (name, run_list, default_attributes,
                override_attributes, env_run_lists))
    except chef.ChefError, exc:
        LOG.debug(
            'Role management failed. Chef Error: %s. Retrying.' % exc)
        manage_role.retry(exc=exc)
    except Exception, exc:
        LOG.debug('Role management failed. Error: %s. Retrying.' % exc)
        manage_role.retry(exc=exc)


@task
def manage_env(deployment, name, desc=None, versions=None,
               default_attributes=None, override_attributes=None):
    match_celery_logging(LOG)
    try:
        api = chef.autoconfigure(
                base_path=os.environ.get('CHECKMATE_CHEF_PATH'))
        e = chef.Environment(name, api=api)
        if desc is not None:
            e.description = desc
        if versions is not None:
            e.cookbook_versions = versions
        if default_attributes is not None:
            e.default_attributes = default_attributes
        if override_attributes is not None:
            e.override_attributes = override_attributes
        e.save()
        LOG.debug("Environment %s updated. Description set to %s "
            "Versions set to %s. Default attributes set to %s. Override "
            "attributes set to %s." % (name, desc, versions,
                  default_attributes, override_attributes))
        return True
    except chef.ChefError, exc:
        LOG.debug(
            'Environment management failed. Chef Error: %s. Retrying.' % exc)
        manage_env.retry(exc=exc)
    except Exception, exc:
        LOG.debug('Environment management failed. Error: %s. Retrying.'
            % exc)
        manage_env.retry(exc=exc)
