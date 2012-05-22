"""
  Celery tasks to orchestrate a sohpisticated deployment
"""
import logging
import time

from celery.app import app_or_default
from celery.task import task
from celery import current_app
assert current_app.backend.__class__.__name__ == 'DatabaseBackend'
assert 'python-stockton' in current_app.backend.dburi.split('/')

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

from checkmate.db import get_driver
from checkmate.utils import extract_sensitive_data

LOG = logging.getLogger(__name__)


@task
def distribute_create_simple_server(deployment, name, image=214, flavor=1,
                                    files=None, ip_address_type='public',
                                    timeout=60):
    """Create a Rackspace Cloud server using a workflow.

    The workflow right now is a simple proof of concept using SPiffWorkflow.
    The workflow spec looks like this::

        Start
            -> Celery: Call Stockton Authentication (gets token)
                -> Transform: write Auth Data into 'deployment' dict
                    -> Celery: Call Stockton Create Server (gets IP)
                        -> End

    Note:: this requires the SpiffWorkflow version with a Celery spec in it,
    which is available here until it is merged in::

            https://github.com/ziadsawalha/SpiffWorkflow/tree/celery
    """

    # Build a workflow spec (the spec is the design of the workflow)
    wfspec = WorkflowSpec(name="Auth and Create Server Workflow")

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

    # Third task takes the 'deployment' attribute and creates a server
    create_server_task = Celery(wfspec, 'Create Server',
                       'stockton.server.distribute_create',
                       call_args=[Attrib('deployment'), name],
                       api_object=None, image=119, flavor=1, files=files,
                       ip_address_type='public')
    write_token.connect(create_server_task)

    # Create an instance of the workflow spec
    wf = Workflow(wfspec)
    #Pass in the initial deployemnt dict (task 3 is the Auth task)
    wf.get_task(3).set_attribute(deployment=deployment)

    db = get_driver('checkmate.db.sql.Driver')
    serializer = DictionarySerializer()
    db.save_workflow(distribute_create_simple_server.request.id,
                     wf.serialize(serializer))

    # Loop through trying to complete the workflow and periodically send
    # status updates
    i = 0
    complete = 0
    total = len(wf.get_tasks(state=Task.ANY_MASK))
    while not wf.is_completed() and i < timeout:
        count = len(wf.get_tasks(state=Task.COMPLETED))
        if count != complete:
            complete = count
            distribute_create_simple_server.update_state(state="PROGRESS",
                                      meta={'complete': count, 'total': total})
        wf.complete_all()
        i += 1
        db.save_workflow(distribute_create_simple_server.request.id,
                     wf.serialize(serializer))
        time.sleep(1)

    db.save_workflow(distribute_create_simple_server.request.id,
                     wf.serialize(serializer))

    return wf.get_task(5).attributes


@task
def distribute_count_seconds(seconds):
    """ just for debugging and testing long-running tasks and updates """
    elapsed = 0
    while elapsed < seconds:
        time.sleep(1)
        elapsed += 1
        distribute_count_seconds.update_state(state="PROGRESS",
                                   meta={'complete': elapsed,
                                         'total': seconds})
    return seconds


@task
def distribute_run_workflow(id, timeout=60):
    """Loop through trying to complete the workflow and periodically send
    status updates"""

    from checkmate.db import get_driver

    db = get_driver('checkmate.db.sql.Driver')
    serializer = DictionarySerializer()
    LOG.debug("Deserializing workflow %s" % id)
    workflow = db.get_workflow(id, with_secrets=True)
    wf = Workflow.deserialize(serializer, workflow)

    LOG.debug("Deserialized workflow %s: %s" % (id, wf.get_dump()))

    i = 0
    last_reported_complete = 0
    wait = 0  # How long to wait (increases with no activity until 6s)
    while not wf.is_completed() and i < timeout:
        total = len(wf.get_tasks(state=Task.ANY_MASK))  # Changes
        count = len(wf.get_tasks(state=Task.COMPLETED))
        if count != last_reported_complete:
            last_reported_complete = count
            LOG.debug("Workflow status: %s/%s (state=%s)" % (count, total,
                    "PROGRESS"))
            LOG.debug(wf.get_dump())
            wait = 1
        else:
            if wait < 6:
                wait += 1
        wf.complete_all()
        i += 1
        workflow = wf.serialize(serializer)
        body, secrets = extract_sensitive_data(workflow)
        db.save_workflow(id, body, secrets)
        LOG.debug("Finished loop #%s for workflow %s (timeout in %is, waiting "
                "%i)" % (i, id, timeout - i, wait))
        time.sleep(wait)

    return workflow


@task
def distribute_run_one_task(workflow_id, task_id, timeout=60):
    """Attempt to complete one task.

    returns True/False indicating if task completed"""

    from checkmate.db import get_driver

    db = get_driver('checkmate.db.sql.Driver')
    serializer = DictionarySerializer()
    LOG.debug("Deserializing workflow %s" % workflow_id)
    workflow = db.get_workflow(workflow_id, with_secrets=True)
    if not workflow:
        raise IndexError("Workflow %s not found" % workflow_id)
    wf = Workflow.deserialize(serializer, workflow)
    task = wf.get_task(task_id)
    if not task:
        raise IndexError("Task %s not found in Workflow %s" % (task_id,
                workflow_id))
    if task._is_finished():
        raise ValueError("Task %s is in state '%s' which cannot be executed" %
            (task_id, task.get_state_name()))

    if task._is_predicted() or task._has_state(Task.WAITING):
        result = task.task_spec._update_state(task)
    elif task._has_state(Task.READY):
        result = wf.complete_task_from_id(task_id)
    else:
        LOG.warn("Task %s in Workflow %s is in state %s and cannot be "
                "progressed" % (task_id, workflow_id, task.get_state_name()))
        return False
    LOG.debug("Task %s in Workflow %s completion result: %s" % (task_id,
            workflow_id, result))
    msg = "Saving: %s" % wf.get_dump()
    LOG.debug(msg)
    workflow = wf.serialize(serializer)
    body, secrets = extract_sensitive_data(workflow)
    db.save_workflow(workflow_id, body, secrets)
    return result


class Orchestrator(object):
    def __init__(self, deployment, auth):
        """ auth object is passed but not used yet. """
        self.deployment = deployment
        self.auth = auth
