""" Workflow handling

This module uses SpiffWorkflow to create, mange, and run workflows for
CheckMate
"""
# pylint: disable=E0611
from bottle import get, post, put, request, response, abort
import logging
import os
import random
import string
import uuid

try:
    from SpiffWorkflow.specs import WorkflowSpec, Celery, Transform, Merge
except ImportError:
    #TODO(zns): remove this when Spiff incorporates the code in it
    print "Get SpiffWorkflow with the Celery spec in it from here: "\
            "https://github.com/ziadsawalha/SpiffWorkflow/tree/celery"
    raise

from SpiffWorkflow import Workflow, Task
from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.storage import DictionarySerializer
from checkmate.db import get_driver, any_id_problems
from checkmate.environments import Environment
from checkmate.utils import write_body, read_body, extract_sensitive_data,\
        merge_dictionary
from checkmate import orchestrator

db = get_driver('checkmate.db.sql.Driver')

LOG = logging.getLogger(__name__)


#
# Workflows
#
@get('/workflows')
@get('/<tenant_id>/workflows')
def get_workflows(tenant_id=None):
    return write_body(db.get_workflows(tenant_id=tenant_id), request, response)


@post('/workflows')
@post('/<tenant_id>/workflows')
def add_workflow(tenant_id=None):
    entity = read_body(request)
    if 'workflow' in entity and isinstance(entity['workflow'], dict):
        entity = entity['workflow']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        abort(406, any_id_problems(entity['id']))

    body, secrets = extract_sensitive_data(entity)
    results = db.save_workflow(entity['id'], body, secrets=secrets,
            tenant_id=tenant_id)

    return write_body(results, request, response)


@post('/workflows/<id>')
@put('/workflows/<id>')
@post('/<tenant_id>/workflows/<id>')
@put('/<tenant_id>/workflows/<id>')
def save_workflow(id, tenant_id=None):
    entity = read_body(request)

    if 'workflow' in entity and isinstance(entity['workflow'], dict):
        entity = entity['workflow']

    if any_id_problems(id):
        abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    body, secrets = extract_sensitive_data(entity)
    results = db.save_workflow(id, body, secrets, tenant_id=tenant_id)

    return write_body(results, request, response)


@get('/workflows/<id>')
@get('/<tenant_id>/workflows/<id>')
def get_workflow(id, tenant_id=None):
    if 'with_secrets' in request.query:  # TODO: verify admin-ness
        entity = db.get_workflow(id, with_secrets=True)
    else:
        entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)
    if 'id' not in entity:
        entity['id'] = str(id)
    return write_body(entity, request, response)


@get('/workflows/<id>/status')
@get('/<tenant_id>/workflows/<id>/status')
def get_workflow_status(id, tenant_id=None):
    entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)
    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, entity)
    return write_body(get_SpiffWorkflow_status(wf), request, response)


@get('/workflows/<id>/+execute')
@get('/<tenant_id>/workflows/<id>/+execute')
def execute_workflow(id, tenant_id=None):
    """Process a checkmate deployment workflow

    Executes and moves the workflow forward.
    Retrieves results (final or intermediate) and updates them into
    deployment.

    :param id: checkmate workflow id
    """
    entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)

    async_call = orchestrator.distribute_run_workflow.delay(id, timeout=10)
    #Wait for call
    async_call.wait()
    entity = db.get_workflow(id)
    return write_body(entity, request, response)


#
# Workflow Tasks
#

@get('/workflows/<id>/tasks/<task_id:int>')
@get('/<tenant_id>/workflows/<id>/tasks/<task_id:int>')
def get_workflow_task(id, task_id, tenant_id=None):
    """Get a workflow task

    :param id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """
    if 'with_secrets' in request.query:  # TODO: verify admin-ness
        entity = db.get_workflow(id, with_secrets=True)
    else:
        entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)

    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, entity)

    task = wf.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)
    data = serializer._serialize_task(task, skip_children=True)
    data['workflow_id'] = id  # so we know which workflow it came from
    return write_body(data, request, response)


@post('/workflows/<id>/tasks/<task_id:int>')
@post('/<tenant_id>/workflows/<id>/tasks/<task_id:int>')
def post_workflow_task(id, task_id, tenant_id=None):
    """Update a workflow task

    Attributes that can be updated are:
    - attributes
    - state
    - internal_attributes

    :param id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """
    entity = read_body(request)

    # Extracting with secrets
    workflow = db.get_workflow(id, with_secrets=True)
    if not workflow:
        abort(404, 'No workflow with id %s' % id)

    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, workflow)

    task = wf.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)

    if 'attributes' in entity:
        if not isinstance(entity['attributes'], dict):
            abort(406, "'attribues' must be a dict")
        # Don't do a simple overwrite since incoming may not have secrets and
        # we don't want to stomp on them
        body, secrets = extract_sensitive_data(task.attributes)
        updated = merge_dictionary(secrets or {}, entity['attributes'])
        task.attributes = updated

    if 'internal_attributes' in entity:
        if not isinstance(entity['internal_attributes'], dict):
            abort(406, "'internal_attribues' must be a dict")
        task.internal_attributes = entity['internal_attributes']

    if 'state' in entity:
        if not isinstance(entity['state'], (int, long)):
            abort(406, "'state' must be an int")
        task._state = entity['state']

    # Save workflow (with secrets)
    serializer = DictionarySerializer()
    body, secrets = extract_sensitive_data(wf.serialize(serializer))

    updated = db.save_workflow(id, body, secrets)
    # Updated does not have secrets, so we deserialize that
    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, updated)
    task = wf.get_task(task_id)
    results = serializer._serialize_task(task, skip_children=True)
    results['workflow_id'] = id
    return write_body(results, request, response)


@get('/workflows/<id>/tasks/<task_id:int>/+reset')
@get('/<tenant_id>/workflows/<id>/tasks/<task_id:int>/+reset')
def reset_workflow_task(id, task_id, tenant_id=None):
    """Reset a Celery workflow task and retry it

    Checks if task is a celery task in waiting state.
    Resets parent to READY and task to FUTURE.
    Removes existing celery task ID.

    :param id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """

    workflow = db.get_workflow(id, with_secrets=True)
    if not workflow:
        abort(404, 'No workflow with id %s' % id)

    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, workflow)

    task = wf.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)

    if task.task_spec.__class__.__name__ != 'Celery':
        abort(406, "You can only reset Celery tasks. This is a '%s' task" %
            task.task_spec.__class__.__name__)

    if task.state != Task.WAITING:
        abort(406, "You can only reset WAITING tasks. This task is in '%s'" %
            task.get_state_name())

    task.task_spec._clear_celery_task_data(task)

    task._state = Task.FUTURE
    task.parent._state = Task.READY

    serializer = DictionarySerializer()
    entity = wf.serialize(serializer)
    body, secrets = extract_sensitive_data(entity)
    db.save_workflow(id, body, secrets)

    task = wf.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)

    # Return cleaned data (no credentials)
    data = serializer._serialize_task(task, skip_children=True)
    body, secrets = extract_sensitive_data(data)
    body['workflow_id'] = id  # so we know which workflow it came from
    return write_body(body, request, response)


@get('/workflows/<id>/tasks/<task_id:int>/+resubmit')
@get('/<tenant_id>/workflows/<id>/tasks/<task_id:int>/+resubmit')
def resubmit_workflow_task(id, task_id, tenant_id=None):
    """Reset a Celery workflow task and retry it

    Checks if task is a celery task in waiting state.
    Clears Celery info and retries the task.

    :param id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """

    workflow = db.get_workflow(id, with_secrets=True)
    if not workflow:
        abort(404, 'No workflow with id %s' % id)

    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, workflow)

    task = wf.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)

    if task.task_spec.__class__.__name__ != 'Celery':
        abort(406, "You can only reset Celery tasks. This is a '%s' task" %
            task.task_spec.__class__.__name__)

    if task.state != Task.WAITING:
        abort(406, "You can only reset WAITING tasks. This task is in '%s'" %
            task.get_state_name())

    task.task_spec.retry_fire(task)

    serializer = DictionarySerializer()
    entity = wf.serialize(serializer)
    body, secrets = extract_sensitive_data(entity)
    db.save_workflow(id, body, secrets)

    task = wf.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)

    # Return cleaned data (no credentials)
    data = serializer._serialize_task(task, skip_children=True)
    body, secrets = extract_sensitive_data(data)
    body['workflow_id'] = id  # so we know which workflow it came from
    return write_body(body, request, response)


@get('/workflows/<id>/tasks/<task_id:int>/+execute')
@get('/<tenant_id>/workflows/<id>/tasks/<task_id:int>/+execute')
def execute_workflow_task(id, task_id, tenant_id=None):
    """Process a checkmate deployment workflow task

    :param id: checkmate workflow id
    :param task_id: task id
    """
    entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)

    #Synchronous call
    orchestrator.distribute_run_one_task(id, task_id, timeout=10)
    entity = db.get_workflow(id)

    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, entity)

    task = wf.get_task(task_id)
    data = serializer._serialize_task(task, skip_children=True)
    data['workflow_id'] = id  # so we know which workflow it came from
    return write_body(data, request, response)


#
# Workflow functions
#
def get_SpiffWorkflow_status(workflow):
    """
    Returns the subtree as a string for debugging.

    :param workflow: a SpiffWorkflow Workflow
    @rtype:  dict
    @return: The debug information.
    """
    def get_task_status(task, output):
        """Recursively fills task data into dict"""
        my_dict = {}
        my_dict['id'] = task.id
        my_dict['threadId'] = task.thread_id
        my_dict['state'] = task.get_state_name()
        output[task.get_name()] = my_dict
        for child in task.children:
            get_task_status(child, my_dict)

    result = {}
    task = workflow.task_tree
    get_task_status(task, result)
    return result


def create_workflow(deployment):
    """Creates a SpiffWorkflow from a CheckMate deployment dict
    :returns: SpiffWorkflow.Workflow"""
    blueprint = deployment['blueprint']
    inputs = deployment['inputs']
    environment = deployment.get('environment')
    if not environment:
        abort(406, "Environment not found. Nowhere to deploy to.")
    environment = Environment(environment)

    # Build a workflow spec (the spec is the design of the workflow)
    wfspec = WorkflowSpec(name="%s Workflow" % blueprint['name'])

    # First task will read 'deployment' attribute and send it to Stockton
    auth_task = Celery(wfspec, 'Authenticate',
                       'stockton.auth.distribute_get_token',
                       call_args=[Attrib('deployment')], result_key='token')
    wfspec.start.connect(auth_task)

    # Second task will take output from first task (the 'token') and write it
    # into the 'deployment' dict to be available to future tasks
    write_token = Transform(wfspec, "Write Token to Deployment", transforms=[
            "my_task.attributes['deployment']['authtoken']"\
            "=my_task.attributes['token']"])
    auth_task.connect(write_token)

    #TODO: make this smarter
    creds = [p['credentials'][0] for key, p in
            deployment['environment']['providers'].iteritems()
            if key == 'common'][0]

    stockton_deployment = {
        'id': deployment['id'],
        'username': creds['username'],
        'apikey': creds['apikey'],
        'region': inputs['region'],
        'files': {}
    }

    keys = []
    # Read in the public keys to be passed to newly created servers.
    if 'public_key' in inputs:
        keys.append(inputs['public_key'])
    if ('CHECKMATE_PUBLIC_KEY' in os.environ and
            os.path.exists(os.path.expanduser(
                os.environ['CHECKMATE_PUBLIC_KEY']))):
        try:
            f = open(os.path.expanduser(os.environ['CHECKMATE_PUBLIC_KEY']))
            keys.append(f.read())
            f.close()
        except IOError as (errno, strerror):
            LOG.error("I/O error reading public key from CHECKMATE_PUBLIC_KEY="
                    "'%s' environment variable (%s): %s" % (
                            os.environ['CHECKMATE_PUBLIC_KEY'], errno,
                                                                strerror))
        except StandardError as exc:
            LOG.error("Error reading public key from CHECKMATE_PUBLIC_KEY="
                    "'%s' environment variable: %s" % (
                            os.environ['CHECKMATE_PUBLIC_KEY'], exc))
    if ('STOCKTON_PUBLIC_KEY' in os.environ and
            os.path.exists(os.path.expanduser(
                os.environ['STOCKTON_PUBLIC_KEY']))):
        try:
            f = open(os.path.expanduser(os.environ['STOCKTON_PUBLIC_KEY']))
            keys.append(f.read())
            f.close()
        except IOError as (errno, strerror):
            LOG.error("I/O error reading public key from STOCKTON_PUBLIC_KEY="
                    "'%s' environment variable (%s): %s" % (
                            os.environ['STOCKTON_PUBLIC_KEY'], errno,
                                                                strerror))
        except StandardError as exc:
            LOG.error("Error reading public key from STOCKTON_PUBLIC_KEY="
                    "'%s' environment variable: %s" % (
                            os.environ['STOCKTON_PUBLIC_KEY'], exc))
    if keys:
        stockton_deployment['files']['/root/.ssh/authorized_keys'] = \
                "\n".join(keys)
    else:
        LOG.warn("No public keys detected. Less secure password auth will be "
                "used.")

    #
    # Create the tasks that make the async calls
    #
    config_provider_type = None
    config_provider = environment.select_provider(resource='configuration')
    if config_provider:
        config_provider_type = config_provider.dict.get('type', 'chef-local')
        if config_provider_type == 'chef-local':
            # TODO: remove this hard-coding to Chef
            create_environment = Celery(wfspec, 'Create Chef Environment',
                    'stockton.cheflocal.distribute_create_environment',
                    call_args=[deployment['id']])
            auth_task.connect(create_environment)

            create_build_role = Celery(wfspec, 'Create Build Role',
                    'stockton.cheflocal.distribute_manage_role',
                    call_args=['build-ks', deployment['id']],
                    run_list=["recipe[apt]",
                              "recipe[build-essential]"],
                    desc="This chef-solo role runs once at build time "
                            "(bootstrap)")
            create_environment.connect(create_build_role)

        elif config_provider_type == 'chef-server':
            # TODO: remove this hard-coding to Chef
            create_environment = Celery(wfspec, 'Create Chef Environment',
                               'stockton.chefserver.distribute_manage_env',
                               call_args=[Attrib('deployment'), deployment['id'],
                                    'CheckMate Environment'])
            auth_task.connect(create_environment)
        else:
            raise NotImplementedError("Config provider '%s' not supported" %
                    config_provider_type)

            create_lb_task = None

    # For resources we create, we store the resource key in the spec's Defines
    # Hard-coding some logic for now:
    # we need to remember bootstrap join tasks so we can make them wait for the
    # database task to complete and populate the chef environment before they
    # run

    bootstrap_joins = []

    for key in deployment['resources']:
        resource = deployment['resources'][key]
        hostname = resource.get('dns-name')
        if resource.get('type') == 'server':
            # Third task takes the 'deployment' attribute and creates a server
            create_server_task = Celery(wfspec, 'Create Server:%s' % key,
                               'stockton.server.distribute_create',
                               call_args=[Attrib('deployment'), hostname],
                               api_object=None,
                               image=resource.get('image', 119),
                               flavor=resource.get('flavor', 1),
                               files=stockton_deployment['files'],
                               ip_address_type='public',
                               defines={"Resource": key})
            write_token.connect(create_server_task)

            # Then register in Chef
            if config_provider_type == 'chef-local':
                ssh_wait_task = Celery(wfspec, 'Wait for Server:%s' % key,
                                   'stockton.ssh.ssh_up',
                                    call_args=[Attrib('deployment'),
                                        Attrib('ip'), 'root'],
                                    password=Attrib('password'),
                                    identity_file=os.environ.get(
                                            'CHECKMATE_PRIVATE_KEY',
                                            '~/.ssh/id_rsa'))
                create_server_task.connect(ssh_wait_task)

                register_node_task = Celery(wfspec, 'Register Server:%s' % key,
                               'stockton.cheflocal.distribute_register_node',
                               call_args=[Attrib('ip'), deployment['id']],
                               password=Attrib('password'),
                               defines={"Resource": key})

                # Register only when server is up and environment is ready
                join = Merge(wfspec, "Wait for Server Build:%s" % key)
                join.connect(register_node_task)
                ssh_wait_task.connect(join)
                create_environment.connect(join)

                bootstrap_task = Celery(wfspec, 'Configure Server:%s' % key,
                       'stockton.cheflocal.distribute_cook',
                        call_args=[Attrib('ip'), deployment['id']],
                        roles=['build-ks', 'wordpress-web'],
                        password=Attrib('password'),
                        identity_file=os.environ.get(
                            'CHECKMATE_PRIVATE_KEY',
                            '~/.ssh/id_rsa'))
                join = Merge(wfspec, "Wait on Server and Settings:%s" % key)
                join.connect(bootstrap_task)
                register_node_task.connect(join)

                bootstrap_joins.append(join)  # to wire up overrides
            elif config_provider_type == 'chef-server':
                register_node_task = Celery(wfspec, 'Register Server:%s' % key,
                               'stockton.chefserver.distribute_register_node',
                               call_args=[Attrib('deployment'), hostname,
                                    ['wordpress-web']],
                                environment=deployment['id'],
                               defines={"Resource": key})
                create_environment.connect(register_node_task)

                ssh_wait_task = Celery(wfspec, 'Wait for Server:%s' % key,
                                   'stockton.ssh.ssh_up',
                                    call_args=[Attrib('deployment'),
                                        Attrib('ip'), 'root'],
                                    password=Attrib('password'),
                                    identity_file=os.environ.get(
                                            'CHECKMATE_PRIVATE_KEY',
                                            '~/.ssh/id_rsa'))
                create_server_task.connect(ssh_wait_task)

                ssh_apt_get_task = Celery(wfspec, 'Apt-get Fix:%s' % key,
                                   'stockton.ssh.ssh_execute',
                                    call_args=[Attrib('ip'),
                                            "sudo apt-get update",
                                            'root'],
                                    password=Attrib('password'),
                                    identity_file=os.environ.get(
                                            'CHECKMATE_PRIVATE_KEY',
                                            '~/.ssh/id_rsa'))
                ssh_wait_task.connect(ssh_apt_get_task)

                bootstrap_task = Celery(wfspec, 'Bootstrap Server:%s' % key,
                                   'stockton.chefserver.distribute_bootstrap',
                                    call_args=[Attrib('deployment'), hostname,
                                    Attrib('ip')],
                                    password=Attrib('password'),
                                    identity_file=os.environ.get(
                                            'CHECKMATE_PRIVATE_KEY',
                                            '~/.ssh/id_rsa'),
                                    run_roles=['build', 'wordpress-web'],
                                    environment=deployment['id'])
                join = Merge(wfspec, "Wait for Server Build:%s" % key)
                join.connect(bootstrap_task)
                ssh_apt_get_task.connect(join)
                register_node_task.connect(join)
                bootstrap_joins.append(join)  # to wire up later to overrides

        elif resource.get('type') == 'load-balancer':
            # Third task takes the 'deployment' attribute and creates a lb
            create_lb_task = Celery(wfspec, 'Create LB',
                               'stockton.lb.distribute_create_loadbalancer',
                               call_args=[Attrib('deployment'), hostname,
                                    'PUBLIC', 'HTTP', 80],
                               dns=True,
                               defines={"Resource": key})
            write_token.connect(create_lb_task)
        elif resource.get('type') == 'database':
            # Third task takes the 'deployment' attribute and creates a server
            start_with = string.ascii_uppercase + string.ascii_lowercase
            password = '%s%s' % (random.choice(start_with),
                    ''.join(random.choice(start_with + string.digits + '@?#_')
                    for x in range(11)))
            db_name = 'db1'
            username = 'wp_user_%s' % db_name
            create_db_task = Celery(wfspec, 'Create DB',
                               'stockton.db.distribute_create_instance',
                               call_args=[Attrib('deployment'), hostname, 1,
                                        resource.get('flavor', 1),
                                        [{'name': db_name}]],
                               update_chef=True,
                               defines={"Resource": key})
            write_token.connect(create_db_task)

            create_db_user = Celery(wfspec, "Add DB User:%s" % username,
                               'stockton.db.distribute_add_user',
                               call_args=[Attrib('deployment'),
                                        Attrib('id'), [db_name],
                                        username, password])
            create_db_task.connect(create_db_user)

            # Then register in Chef

            # TODO: fix hard-coding DB (this should be triggered by a
            # relation) Take output from Create DB task and write it into
            # the 'override' dict to be available to future tasks

            compile_override = Transform(wfspec, "Prepare Overrides",
                    transforms=[
                    "my_task.attributes['overrides']={'wordpress': {'db': "
                    "{'host': my_task.attributes['hostname'], "
                    "'database': '%s', 'user': '%s', 'password': '%s'}}}" %
                            (db_name, username, password)])
            create_db_user.connect(compile_override)

            # Set environment databag
            if config_provider_type == 'chef-local':
                set_overrides = Celery(wfspec,
                        'Create Wordpress Role',
                        'stockton.cheflocal.distribute_manage_role',
                        call_args=['wordpress-web', deployment['id']],
                        run_list=["recipe[wordpress]"],
                        override_attributes=Attrib('overrides'))
            elif config_provider_type == 'chef-server':
                set_overrides = Celery(wfspec,
                        "Write Database Settings",
                        'stockton.chefserver.distribute_manage_env',
                        call_args=[Attrib('deployment'), deployment['id']],
                            desc='CheckMate Environment',
                            override_attributes=Attrib('overrides'))
            join = Merge(wfspec, "Wait on Environment and Settings:%s" % key)
            join.connect(set_overrides)
            create_environment.connect(join)
            compile_override.connect(join)

        elif resource.get('type') == 'dns':
            # TODO: NOT TESTED YET
            create_dns_task = Celery(wfspec, 'Create DNS Record',
                               'stockton.dns.distribute_create_record',
                               call_args=[Attrib('deployment'),
                               inputs.get('domain', 'localhost'), hostname,
                               'A', Attrib('vip')],
                               defines={"Resource": key})
        else:
            pass

    # Wire connections
    #TODO: remove this hard-coding and use relations
    for bootstrap_join in bootstrap_joins:
        set_overrides.connect(bootstrap_join)

    if create_lb_task:
        specs = {}
        for name, task_spec in wfspec.task_specs.iteritems():
            if name.startswith('Bootstrap Server') or\
                    name.startswith('Configure Server'):
                specs[name] = task_spec
        for name, task_spec in specs.iteritems():
            # Wire to LB
            save_lbid = Transform(wfspec, "Get LB ID:%s" % name.split(':')[1],
                    transforms=[
                    "my_task.attributes['lbid']=my_task.attributes['id']"])
            create_lb_task.connect(save_lbid)
            add_node = Celery(wfspec,
                    "Add LB Node:%s" % name.split(':')[1],
                    'stockton.lb.distribute_add_node',
                    call_args=[Attrib('deployment'),  Attrib('lbid'),
                            Attrib('ip'), 80])
            join = Merge(wfspec, "Wait for LB:%s" % name.split(':')[1])
            join.connect(add_node)
            save_lbid.connect(join)
            task_spec.connect(join)

    wf = Workflow(wfspec)
    #Pass in the initial deployemnt dict (task 2 is the Start task)
    wf.get_task(2).set_attribute(deployment=stockton_deployment)
    return wf
