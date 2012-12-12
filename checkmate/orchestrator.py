"""
  Celery tasks to orchestrate a sophisticated deployment
"""
import logging
import time

from celery.task import task

try:
    from SpiffWorkflow.specs import WorkflowSpec, Celery, Transform
except ImportError:
    #TODO(zns): remove this when Spiff incorporates the code in it
    print "Get SpiffWorkflow with the Celery spec in it from here: "\
          "https://github.com/ziadsawalha/SpiffWorkflow/"
    raise
from SpiffWorkflow import Workflow, Task
from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.storage import DictionarySerializer

from checkmate.db import get_driver
from checkmate.middleware import RequestContext
from checkmate.utils import extract_sensitive_data, match_celery_logging

LOG = logging.getLogger(__name__)
DB = get_driver()


@task
def create_simple_server(context, name, image=119, flavor=1,
                         files=None, ip_address_type='public',
                         timeout=60):
    """Create a Rackspace Cloud server using a workflow.

    The workflow right now is a simple proof of concept using SPiffWorkflow.
    The workflow spec looks like this::

        Start
            -> Celery: Call Stockton Authentication (gets token)
                -> Transform: write Auth Data into 'context' dict
                    -> Celery: Call Stockton Create Server (gets IP)
                        -> End

    Note:: this requires the SpiffWorkflow version with a Celery spec in it,
    which is available here until it is merged in::

            https://github.com/ziadsawalha/SpiffWorkflow/tree/celery
    """
    match_celery_logging(LOG)
    # Build a workflow spec (the spec is the design of the workflow)
    wfspec = WorkflowSpec(name="Auth and Create Server Workflow")

    # First task will read 'context' attribute and send it to Stockton
    auth_task = Celery(wfspec, 'Authenticate',
                       'checkmate.providers.rackspace.identity.get_token',
                       call_args=[Attrib('context')], result_key='token')
    wfspec.start.connect(auth_task)

    # Second task will take output from first task (the 'token') and write it
    # into the 'context' dict to be available to future tasks
    write_token = (Transform(wfspec, "Write Token to Deployment", transforms=[
                   "my_task.attributes['context']['authtoken']"
                   "=my_task.attributes['token']"]))
    auth_task.connect(write_token)

    # Third task takes the 'context' attribute and creates a server
    create_server_task = (Celery(wfspec, 'Create Server',
                          'checkmate.providers.rackspace. \
                          compute_legacy.create_server',
                          call_args=[Attrib('context'), name],
                          api_object=None, image=image, flavor=flavor,
                          files=files,
                          ip_address_type=ip_address_type))
    write_token.connect(create_server_task)

    # Create an instance of the workflow spec
    workflow = Workflow(wfspec)
    #Pass in the initial deployemnt dict (task 3 is the Auth task)
    workflow.get_task(3).set_attribute(context=context)

    serializer = DictionarySerializer()
    body = workflow.serialize(serializer)
    body['id'] = create_simple_server.request.id
    DB.save_workflow(create_simple_server.request.id,
                     body)

    # Loop through trying to complete the workflow and periodically send
    # status updates
    i = 0
    complete = 0
    total = len(workflow.get_tasks(state=Task.ANY_MASK))
    while not workflow.is_completed() and i < timeout:
        count = len(workflow.get_tasks(state=Task.COMPLETED))
        if count != complete:
            complete = count
            create_simple_server.update_state(state="PROGRESS",
                                              meta={'complete': count,
                                              'total': total})
        workflow.complete_all()
        i += 1
        DB.save_workflow(create_simple_server.request.id,
                         workflow.serialize(serializer))
        time.sleep(1)

    DB.save_workflow(create_simple_server.request.id,
                     workflow.serialize(serializer))

    return workflow.get_task(5).attributes


@task
def count_seconds(seconds):
    """ just for debugging and testing long-running tasks and updates """
    match_celery_logging(LOG)
    elapsed = 0
    while elapsed < seconds:
        time.sleep(1)
        elapsed += 1
        count_seconds.update_state(state="PROGRESS",
                                   meta={'complete': elapsed,
                                         'total': seconds})
    return seconds


@task(default_retry_delay=10, max_retries=300)
def run_workflow(w_id, timeout=900, wait=1, counter=1):
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
    match_celery_logging(LOG)
    # Get the workflow
    serializer = DictionarySerializer()
    workflow = DB.get_workflow(w_id, with_secrets=True)
    d_wf = Workflow.deserialize(serializer, workflow)
    LOG.debug("Deserialized workflow %s" % w_id,
              extra=dict(data=d_wf.get_dump()))

    # Prepare to run it
    if d_wf.is_completed():
        LOG.debug("Workflow '%s' is already complete. Nothing to do." % w_id)
        return True

    before = d_wf.get_dump()

    # Run!
    try:
        d_wf.complete_all()
    except Exception as exc:
        LOG.exception(exc)
        return False
    finally:
        # Save any changes, even if we errored out
        after = d_wf.get_dump()

        if before != after:
            # We made some progress, so save and prioritize next run
            updated = d_wf.serialize(serializer)
            body, secrets = extract_sensitive_data(updated)
            body['tenantId'] = workflow.get('tenantId')
            body['id'] = w_id
            DB.save_workflow(w_id, body, secrets)
            wait = 1

            # Report progress
            total = len(d_wf.get_tasks(state=Task.ANY_MASK))  # Changes
            completed = len(d_wf.get_tasks(state=Task.COMPLETED))
            LOG.debug("Workflow status: %s/%s (state=%s)" % (completed,
                      total, "PROGRESS"))
            run_workflow.update_state(state="PROGRESS",
                                      meta={'complete': completed,
                                      'total': total})
        else:
            # No progress made. So drop priority (to max of 20s wait)
            if wait < 20:
                wait += 1
            LOG.debug("Workflow '%s' did not make any progress. "
                      "Deprioritizing it and waiting %s seconds to retry."
                      % (w_id, wait))

    # Assess impact of run
    if d_wf.is_completed():
        return True

    timeout = timeout - wait if timeout > wait else 0
    if timeout:
        LOG.debug("Finished run of workflow '%s'. %i seconds to go. Waiting "
                  " %i seconds to next run. Retries done: %s" % (w_id,
                                                                 timeout,
                                                                 wait,
                                                                 counter))
        retry_kwargs = {'timeout': timeout, 'wait': wait,
                        'counter': counter + 1}
        return run_workflow.retry([w_id], kwargs=retry_kwargs, countdown=wait,
                                  Throw=False)
    else:
        LOG.debug("Workflow '%s' did not complete (no timeout set)." % w_id)
        return False


@task
def run_one_task(context, workflow_id, task_id, timeout=60):
    """Attempt to complete one task.

    returns True/False indicating if task completed"""
    match_celery_logging(LOG)
    serializer = DictionarySerializer()
    workflow = DB.get_workflow(workflow_id, with_secrets=True)
    if not workflow:
        raise IndexError("Workflow %s not found" % workflow_id)
    LOG.debug("Deserializing workflow '%s'" % workflow_id)
    d_wf = Workflow.deserialize(serializer, workflow)
    task = d_wf.get_task(task_id)
    original = serializer._serialize_task(task, skip_children=True)
    if not task:
        raise IndexError("Task '%s' not found in Workflow '%s'" % (task_id,
                         workflow_id))
    if task._is_finished():
        raise ValueError("Task '%s' is in state '%s' which cannot be executed"
                         % (task.get_name(), task.get_state_name()))

    if task._is_predicted() or task._has_state(Task.WAITING):
        LOG.debug("Progressing task '%s' (%s)" % (task_id,
                                                  task.get_state_name()))
        if isinstance(context, dict):
            context = RequestContext(**context)
        # Refresh token if it exists in args[0]['auth_token]
        if hasattr(task, 'args') and task.task_spec.args and \
                len(task.task_spec.args) > 0 and \
                isinstance(task.task_spec.args[0], dict) and \
                task.task_spec.args[0].get('auth_token') != \
                context.auth_token:
            task.task_spec.args[0]['auth_token'] = context.auth_token
            LOG.debug("Updating task auth token with new caller token")
        result = task.task_spec._update_state(task)
    elif task._has_state(Task.READY):
        LOG.debug("Completing task '%s' (%s)" % (task_id,
                  task.get_state_name()))
        result = d_wf.complete_task_from_id(task_id)
    else:
        LOG.warn("Task '%s' in Workflow '%s' is in state %s and cannot be "
                 "progressed" % (task_id, workflow_id, task.get_state_name()))
        return False
    updated = d_wf.serialize(serializer)
    if original != updated:
        LOG.debug("Task '%s' in Workflow '%s' completion result: %s" % (
                  task_id, workflow_id, result))
        msg = "Saving: %s" % d_wf.get_dump()
        LOG.debug(msg)
        body, secrets = extract_sensitive_data(updated)
        body['tenantId'] = workflow.get('tenantId')
        body['id'] = workflow_id
        DB.save_workflow(workflow_id, body, secrets)
    return result
