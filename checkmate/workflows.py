""" Workflow handling

This module uses SpiffWorkflow to create, manage, and run workflows for
CheckMate
"""
# pylint: disable=E0611
from bottle import get, post, put, request, response, abort
import logging
import os
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
        merge_dictionary, is_ssh_key, with_tenant, get_source_body
from checkmate import orchestrator

db = get_driver('checkmate.db.sql.Driver')

LOG = logging.getLogger(__name__)


#
# Workflows
#
@get('/workflows')
@with_tenant
def get_workflows(tenant_id=None):
    return write_body(db.get_workflows(tenant_id=tenant_id), request, response)


@post('/workflows')
@with_tenant
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
@with_tenant
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
@with_tenant
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
@with_tenant
def get_workflow_status(id, tenant_id=None):
    entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)
    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, entity)
    return write_body(get_SpiffWorkflow_status(wf), request, response)


@get('/workflows/<id>/+execute')
@with_tenant
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
    LOG.debug("Executed run workflow task: %s" % async_call)
    entity = db.get_workflow(id)
    return write_body(entity, request, response)


#
# Workflow Tasks
#

@get('/workflows/<id>/tasks/<task_id:int>')
@with_tenant
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
@with_tenant
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
@with_tenant
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
@with_tenant
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
@with_tenant
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
                       call_args=[Attrib('context')], result_key='token',
                       description="Authenticate and get a token to use with "
                            "other calls. Authentication also gates any "
                            "further work, to make sure we are working on "
                            "behalf of an authenticated client",
                       properties={'estimated_duration': 5})
    wfspec.start.connect(auth_task)

    # Second task will take output from first task (the 'token') and write it
    # into the 'deployment' dict to be available to future tasks
    write_token = Transform(wfspec, "Get Token", transforms=[
            "my_task.attributes['context']['authtoken']"\
            "=my_task.attributes['token']"], description="Get token response "
                    "and write it into context")
    auth_task.connect(write_token)

    #TODO: make this smarter
    creds = [p['credentials'][0] for key, p in
            deployment['environment']['providers'].iteritems()
            if key == 'common'][0]

    keys = get_os_env_keys()
    # Read in the public keys to be passed to newly created servers.
    if 'public_key' in inputs:
        if not is_ssh_key(inputs['public_key']):
            abort("public_key input is not a valid public key string.")
        keys['client'] = {'public_key': inputs['public_key']}
    if not keys:
        LOG.warn("No public keys supplied. Less secure password auth will be "
                "used.")

    context = {
        'id': deployment['id'],
        'username': creds['username'],
        'apikey': creds['apikey'],
        'region': inputs['region'],
        'keys': keys
    }

    #
    # Create the tasks that make the async calls
    #

    # Get list of providers and store them for use throughout
    providers = {}
    for resource_type in ['configuration', 'compute', 'load-balancer',
            'database']:
        provider = environment.select_provider(resource=resource_type)
        if provider:
            providers[resource_type] = provider
            prep_result = provider.prep_environment(wfspec,  deployment)
            # Wire up if not wired in somewhere
            if prep_result and not prep_result['root'].inputs:
                auth_task.connect(prep_result['root'])

    config_provider = providers['configuration']
    compute_provider = providers['compute']
    lb_provider = providers['load-balancer']
    database_provider = providers['database']

    # For resources we create, we store the resource key in the spec's Defines
    # Hard-coding some logic for now:
    # we need to remember bootstrap join tasks so we can make them wait for the
    # database task to complete and populate the chef environment before they
    # run
    # TODO: make bootstrap tasks wait and join based on requires/provides in
    # components and blueprints

    create_lb_task = None

    for key in deployment['resources']:
        resource = deployment['resources'][key]
        hostname = resource.get('dns-name')
        if resource.get('type') == 'server':
            # Third task takes the 'deployment' attribute and creates a server
            compute_result = compute_provider.add_resource_tasks(resource,
                    key, wfspec, deployment, context,
                    wait_on=[config_provider.prep_task])
            write_token.connect(compute_result['root'])

            # NOTE: chef-server provider assums wait_on[0]=create_server_task
            config_provider.add_resource_tasks(
                    resource, key, wfspec, deployment, context,
                    wait_on=[compute_result['final']])

        elif resource.get('type') == 'load-balancer':
            # Third task takes the 'deployment' attribute and creates a lb
            lb_result = lb_provider.add_resource_tasks(resource,
                    key, wfspec, deployment, context)
            write_token.connect(lb_result['root'])
            create_lb_task = lb_result['final']
        elif resource.get('type') == 'database':
            # Third task takes the 'deployment' attribute and creates a server
            db_result = database_provider.add_resource_tasks(resource,
                    key, wfspec, deployment, context)

            write_token.connect(db_result['root'])

            # Register database settings in Chef

            # TODO: fix hard-coding DB (this should be triggered by a
            # relation) Take output from Create DB task and write it into
            # the 'override' dict to be available to future tasks
            compile_override = Transform(wfspec, "Prepare Overrides",
                    transforms=[
                    "my_task.attributes['overrides']={'wordpress': {'db': "
                    "{'host': my_task.attributes['hostname'], "
                    "'database': my_task.attributes['context']['db_name'], "
                    "'user': my_task.attributes['context']['db_username'], "
                    "'password': my_task.attributes['context']"
                    "['db_password']}}}"], description="Get all the variables "
                            "we need (like database name and password) and "
                            "compile them into JSON that we can set on the "
                            "role or environment")
            db_result['final'].connect(compile_override)

            # Set environment databag
            if config_provider.__class__.__name__ == 'LocalProvider':
                set_overrides = Celery(wfspec,
                        'Write Database Settings',
                        'stockton.cheflocal.distribute_manage_role',
                        call_args=['wordpress-web', deployment['id']],
                        override_attributes=Attrib('overrides'),
                        description="Take the JSON prepared earlier and write "
                                "it into the wordpress role. It will be used "
                                "by the Chef recipe to connect to the DB",
                        properties={'estimated_duration': 10})
            elif config_provider.__class__.__name__ == 'ServerProvider':
                set_overrides = Celery(wfspec,
                        "Write Database Settings",
                        'stockton.chefserver.distribute_manage_env',
                        call_args=[Attrib('context'), deployment['id']],
                            desc='CheckMate Environment',
                            override_attributes=Attrib('overrides'),
                        description="Take the JSON prepared earlier and write "
                                "it into the environment overrides. It will "
                                "be used by the Chef recipe to connect to "
                                "the database",
                        properties={'estimated_duration': 15})
            wait_on = [compile_override]
            if config_provider:
                wait_on.append(config_provider.prep_task)
            wait_for(wfspec, set_overrides, wait_on,
                    name="Wait on Environment and Settings:%s" % key)

        elif resource.get('type') == 'dns':
            # TODO: NOT TESTED YET
            create_dns_task = Celery(wfspec, 'Create DNS Record',
                               'stockton.dns.distribute_create_record',
                               call_args=[Attrib('context'),
                               inputs.get('domain', 'localhost'), hostname,
                               'A', Attrib('vip')],
                               defines={"Resource": key},
                               properties={'estimated_duration': 30})
            write_token.connect(create_dns_task)
        else:
            pass

    # Wire connections
    #TODO: remove this hard-coding and use relations
    # Get configure tasks make them preced LB Add Node and make set_overrides
    # preced them
    specs = {}
    for name, task_spec in wfspec.task_specs.iteritems():
        if name.startswith('Bootstrap Server') or\
                name.startswith('Configure Server'):
            specs[name] = task_spec
            # Assuming input is join
            assert isinstance(task_spec.inputs[0], Merge)
            set_overrides.connect(task_spec.inputs[0])

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

            # Get ServiceNet IP and use that
            def get_private_ip(my_task):
                addresses = my_task.attributes.get('addresses', [])
                private_addresses = addresses.get('private', [])
                for address in private_addresses:
                    if address['version'] == 4:
                        my_task.attributes['private_ip'] = address['addr']
                        break

            get_snet_ip = Transform(wfspec,
                                 "Get ServiceNet IP:%s" % name.split(':')[1],
                                 transforms=[get_source_body(get_private_ip)])
            server_up_task = wfspec.get_task_spec_from_name("Check that "
                    "Server is Up:%s" % name.split(':')[1])
            server_up_task.connect(get_snet_ip)

            add_node = Celery(wfspec,
                    "Add LB Node:%s" % name.split(':')[1],
                    'stockton.lb.distribute_add_node',
                    call_args=[Attrib('context'),  Attrib('lbid'),
                            Attrib('private_ip'), 80],
                    properties={'estimated_duration': 20})
            wait_for(wfspec, add_node, [get_snet_ip, task_spec, save_lbid],
                    name="Wait before adding to LB:%s" % name.split(':')[1],
                    description="Wait for Load Balancer ID, ServiceNet IP, "
                            "and for server to be fully configured before "
                            "adding it to load balancer")

    workflow = Workflow(wfspec)
    #Pass in the initial deployemnt dict (task 2 is the Start task)
    workflow.get_task(2).set_attribute(context=context)

    # Calculate estimated_duration
    root = workflow.task_tree
    root._set_internal_attribute(estimated_completed_in=0)
    tasks = root.children[:]
    overall = 0
    while tasks:
        task = tasks.pop(0)
        tasks.extend(task.children)
        expect_to_take = task.parent._get_internal_attribute(
                'estimated_completed_in') +\
                task.task_spec.get_property('estimated_duration', 0)
        if expect_to_take > overall:
            overall = expect_to_take
        task._set_internal_attribute(estimated_completed_in=expect_to_take)
    workflow.attributes['estimated_duration'] = overall

    return workflow


def wait_for(wf_spec, task, wait_list, name=None, description=None):
    """Wires up tasks so that 'task' will wait for all tasks in 'wait_list' to
    complete before proceeding.

    :param wf_spec: the workflow spec being worked on
    :param task: the task that will be waiting
    :param wait_list: a list of tasks to wait on
    :param name: the name of the merge task (autogenerated if not supplied)
    :param description: a description for the wait task
    """
    if not name:
        name = "%s wait on %s" % (task.id, ",".join([t.id for t in wait_list]))
    join = Merge(wf_spec, name, description=description)
    join.connect(task)
    for t in wait_list:
        t.connect(join)
    return join


def get_os_env_keys():
    """Get keys if they are set in the os_environment"""
    keys = {}
    if ('CHECKMATE_PUBLIC_KEY' in os.environ and
            os.path.exists(os.path.expanduser(
                os.environ['CHECKMATE_PUBLIC_KEY']))):
        try:
            path = os.path.expanduser(os.environ['CHECKMATE_PUBLIC_KEY'])
            f = open(path)
            keys['checkmate'] = {'public_key': f.read(),
                    'public_key_path': path}
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
            path = os.path.expanduser(os.environ['STOCKTON_PUBLIC_KEY'])
            f = open(path)
            keys['stockton'] = {'public_key': f.read(),
                    'public_key_path': path}
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
    return keys
