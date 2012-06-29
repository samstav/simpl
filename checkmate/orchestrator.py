"""
  Celery tasks to orchestrate a sophisticated deployment
"""
import logging
import time

from celery import current_app
from celery.contrib.abortable import AbortableTask
from celery.task import task
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
def create_simple_server(deployment, name, image=214, flavor=1,
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
                       'checkmate.providers.rackspace.identity.get_token',
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
           'checkmate.providers.rackspace.compute_legacy.create_server',
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
    db.save_workflow(create_simple_server.request.id,
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
            create_simple_server.update_state(state="PROGRESS",
                                      meta={'complete': count, 'total': total})
        wf.complete_all()
        i += 1
        db.save_workflow(create_simple_server.request.id,
                     wf.serialize(serializer))
        time.sleep(1)

    db.save_workflow(create_simple_server.request.id,
                     wf.serialize(serializer))

    return wf.get_task(5).attributes


@task
def count_seconds(seconds):
    """ just for debugging and testing long-running tasks and updates """
    elapsed = 0
    while elapsed < seconds:
        time.sleep(1)
        elapsed += 1
        count_seconds.update_state(state="PROGRESS",
                                   meta={'complete': elapsed,
                                         'total': seconds})
    return seconds


class run_workflow(AbortableTask):
    track_started = True
    default_retry_delay = 10
    max_retries = 300  # We use our own timeout

    def run(self, id, timeout=60, wait=1, counter=1):
        """Loop through trying to complete the workflow and periodically log
        status updates. Each time we cycle through, if nothing happens we
        extend the wait time between cycles so we don't load the system.

        This function should not consume time, so the timeout is only counting
        the number of seconds we wait between runs

        :param id: the workflow id
        :param timeout: the timeout in seconds. Unless we complete before then
        :param wait: how long to wait between runs. Grows without activity
        :returns: True if workflow is complete
        """

        # Get the workflow
        db = get_driver('checkmate.db.sql.Driver')
        serializer = DictionarySerializer()
        workflow = db.get_workflow(id, with_secrets=True)
        wf = Workflow.deserialize(serializer, workflow)
        LOG.debug("Deserialized workflow %s: %s" % (id, wf.get_dump()))

        # Prepare to run it
        if wf.is_completed():
            return True

        before = wf.get_dump()

        # Run!
        try:
            wf.complete_all()
        except Exception as exc:
            LOG.exception(exc)
            return False
        finally:
            # Save any changes, even if we errored out
            after = wf.get_dump()

            if before != after:
                # We made some progress, so save and prioritize next run
                workflow = wf.serialize(serializer)
                body, secrets = extract_sensitive_data(workflow)
                db.save_workflow(id, body, secrets)
                wait = 1

                # Report progress
                total = len(wf.get_tasks(state=Task.ANY_MASK))  # Changes
                completed = len(wf.get_tasks(state=Task.COMPLETED))
                LOG.debug("Workflow status: %s/%s (state=%s)" % (completed, total,
                        "PROGRESS"))
                self.update_state(state="PROGRESS",
                        meta={'complete': completed, 'total': total})
            else:
                # No progress made. So we lose some priority (to max of 20s wait)
                if wait < 20:
                    wait += 1

        # Assess impact of run
        if wf.is_completed():
            return True

        timeout = timeout - wait if timeout > wait else 0
        if timeout:
            LOG.debug("Finished run of workflow %s. %is to go. Waiting %i to "
                    "next run. Retries: %s" % (id, timeout, wait,
                    counter))
            retry_kwargs = {'timeout': timeout, 'wait': wait,
                    'counter': counter + 1}
            return self.retry([id], kwargs=retry_kwargs, countdown=wait,
                    Throw=False)
        else:
            LOG.debug("Workflow %s timed out." % id)
            return False


@task
def run_one_task(workflow_id, task_id, timeout=60):
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
