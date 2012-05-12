""" Workflow handling

This module uses SpiffWorkflow to create, mange, and run workflows for
CheckMate
"""
# pylint: disable=E0611
from bottle import app, get, post, put, delete, request, \
        response, abort
import logging
import os
import uuid

try:
    from SpiffWorkflow.specs import WorkflowSpec, Celery, Transform
except ImportError:
    #TODO(zns): remove this when Spiff incorporates the code in it
    print "Get SpiffWorkflow with the Celery spec in it from here: "\
            "https://github.com/ziadsawalha/SpiffWorkflow/tree/celery"
    raise

from SpiffWorkflow import Workflow, Task
from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.storage import DictionarySerializer
from checkmate.db import get_driver, any_id_problems, any_tenant_id_problems
from checkmate.utils import write_body, read_body
from checkmate import orchestrator

db = get_driver('checkmate.db.sql.Driver')

LOG = logging.getLogger(__name__)


#
# Workflows
#
@get('/workflows')
def get_workflows():
    return write_body(db.get_workflows(), request, response)


@post('/workflows')
def add_workflow():
    entity = read_body(request)
    if 'workflow' in entity and isinstance(entity['workflow'], dict):
        entity = entity['workflow']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        abort(406, any_id_problems(entity['id']))

    results = db.save_workflow(entity['id'], entity)

    return write_body(results, request, response)


@post('/workflows/<id>')
@put('/workflows/<id>')
def save_workflow(id):
    entity = read_body(request)

    if 'workflow' in entity and isinstance(entity['workflow'], dict):
        entity = entity['workflow']

    if any_id_problems(id):
        abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    results = db.save_workflow(id, entity)

    return write_body(results, request, response)


@get('/workflows/<id>')
def get_workflow(id):
    entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)
    if 'id' not in entity:
        entity['id'] = str(id)
    return write_body(entity, request, response)


@get('/workflows/<id>/status')
def get_workflow_status(id):
    entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)
    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, entity)
    return write_body(get_SpiffWorkflow_status(wf), request, response)


@get('/workflows/<id>/+execute')
def execute_workflow(id):
    """Process a checkmate deployment workflow

    Executes and moves the workflow forward.
    Retrieves results (final or intermediate) and updates them into
    deployment.

    :param id: checkmate workflow id
    """
    entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)

    #Synchronous call
    orchestrator.distribute_run_workflow(id, timeout=10)
    entity = db.get_workflow(id)
    return write_body(entity, request, response)


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


@get('/workflows/<id>/tasks/<task_id:int>/+reset')
def reset_workflow_task(id, task_id):
    """Reset a Celery workflow task and retry it

    Checks if task is a celery task in waiting state.
    Resets parent to READY and task to FUTURE.
    Removes existing celery task ID.

    :param id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """

    workflow = db.get_workflow(id)
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

    if 'task_id' in task.internal_attributes:
        del task.internal_attributes['task_id']
    if 'error' in task.attributes:
        del task.attributes['error']
    task._state = Task.FUTURE
    task.parent._state = Task.READY

    serializer = DictionarySerializer()
    results = db.save_workflow(id, wf.serialize(serializer))

    return write_body(results, request, response)


@get('/workflows/<id>/tasks/<task_id:int>')
def get_workflow_task(id, task_id):
    """Get a workflow task

    :param id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """
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
def post_workflow_task(id, task_id):
    """Update a workflow task

    Attributes that can be updated are:
    - attributes
    - state
    - internal_attributes

    :param id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """
    entity = read_body(request)

    workflow = db.get_workflow(id)
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
        task.attributes = entity['attributes']

    if 'internal_attributes' in entity:
        if not isinstance(entity['internal_attributes'], dict):
            abort(406, "'internal_attribues' must be a dict")
        task.internal_attributes = entity['internal_attributes']

    if 'state' in entity:
        if not isinstance(entity['state'], (int, long)):
            abort(406, "'state' must be an int")
        task._state = entity['state']

    serializer = DictionarySerializer()
    db.save_workflow(id, wf.serialize(serializer))
    task = wf.get_task(task_id)
    results = serializer._serialize_task(task, skip_children=True)
    results['workflow_id'] = id
    return write_body(results, request, response)


@get('/workflows/<id>/tasks/<task_id:int>/+execute')
def execute_workflow_task(id, task_id):
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


def create_workflow(deployment):
    """Creates a SpiffWorkflow from a CheckMate deployment dict
    :returns: SpiffWorkflow.Workflow"""
    blueprint = deployment['blueprint']
    inputs = deployment['inputs']

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
    creds = [p['credentials'][0] for p in
            deployment['environment']['providers'] if 'common' in p][0]

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
        except StandardException as exc:
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
        except StandardException as exc:
            LOG.error("Error reading public key from STOCKTON_PUBLIC_KEY="
                    "'%s' environment variable: %s" % (
                            os.environ['STOCKTON_PUBLIC_KEY'], exc))
    if keys:
        stockton_deployment['files']['/root/.ssh/authorized_keys'] = \
                "\n".join(keys)
    else:
        LOG.warn("No public keys detected. Less secure password auth will be "
                "used.")

    # Create the tasks that make the async calls
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
            register_node_task = Celery(wfspec, 'Register Server:%s' % key,
                               'stockton.chefserver.distribute_register_node',
                               call_args=[Attrib('deployment'), hostname,
                                    ['wordpress-web']],
                               defines={"Resource": key})
            write_token.connect(register_node_task)

            ssh_wait_task = Celery(wfspec, 'Wait for Server:%s' % key,
                               'stockton.ssh.ssh_up',
                                call_args=[Attrib('deployment'), Attrib('ip'),
                                    'root'],
                                password=Attrib('password'),
                                identity_file=os.environ.get(
                                    'CHECKMATE_PRIVATE_KEY', '~/.ssh/id_rsa'),
                               defines={"Resource": key})
            create_server_task.connect(ssh_wait_task)

            bootstrap_task = Celery(wfspec, 'Bootstrap Server:%s' % key,
                               'stockton.chefserver.distribute_bootstrap',
                                call_args=[Attrib('deployment'), hostname,
                                Attrib('ip')],
                                password=Attrib('password'),
                                identity_file=os.environ.get(
                                    'CHECKMATE_PRIVATE_KEY', '~/.ssh/id_rsa'),
                                roles=['wordpress-web'],
                                run_roles=['build'])
            ssh_wait_task.connect(bootstrap_task)

        elif resource.get('type') == 'load-balancer':
            # Third task takes the 'deployment' attribute and creates a lb
            create_lb_task = Celery(wfspec, 'Create LB:%s' % key,
                               'stockton.lb.distribute_create_loadbalancer',
                               call_args=[Attrib('deployment'), hostname,
                                    'PUBLIC', 'HTTP', 80],
                               dns=True,
                               defines={"Resource": key})
            write_token.connect(create_lb_task)
        elif resource.get('type') == 'database':
            # Third task takes the 'deployment' attribute and creates a server
            create_db_task = Celery(wfspec, 'Create DB:%s' % key,
                               'stockton.db.distribute_create_instance',
                               call_args=[Attrib('deployment'), hostname, 1,
                                        resource.get('flavor', 1),
                                        [{'name': 'db1'}]],
                               update_chef=True,
                               defines={"Resource": key})
            write_token.connect(create_db_task)

            create_db_user = Celery(wfspec, 'Add DB User:%s' % key,
                               'stockton.db.distribute_add_user',
                               call_args=[Attrib('deployment'),
                                        Attrib('id'), [{'name': 'db1'}],
                                        'MyDBUser', 'password'])
            create_db_task.connect(create_db_user)

        elif resource.get('type') == 'dns':
            # TODO: NOT TESTED YET
            create_dns_task = Celery(wfspec, 'Create DNS Record:%s' % key,
                               'stockton.dns.distribute_create_record',
                               call_args=[Attrib('deployment'),
                               inputs.get('domain', 'localhost'), hostname,
                               'A', Attrib('vip')],
                               defines={"Resource": key})
        else:
            pass

    wf = Workflow(wfspec)
    #Pass in the initial deployemnt dict (task 3 is the Auth task)
    wf.get_task(3).set_attribute(deployment=stockton_deployment)
    return wf
