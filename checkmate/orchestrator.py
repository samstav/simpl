"""
  Celery tasks to orchestrate a sohpisticated deployment
"""
import syslog
import time
import yaml

from celery.app import app_or_default
from celery.result import AsyncResult
from celery.task import task

try:
    from SpiffWorkflow.specs import Simple, WorkflowSpec, Celery, Transform
except ImportError:
    #TODO(zns): remove this when Spiff incorporates the code in it
    print "Get SpiffWorkflow with the Celery spec in it from here: "\
            "https://github.com/ziadsawalha/SpiffWorkflow/tree/celery"
    raise
from SpiffWorkflow import Workflow, Task
from SpiffWorkflow.operators import Attrib


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
        time.sleep(1)

    return wf.get_task(5).attributes


@task
def get_workflow_status(id):
    """ Returns information about a task.
    :param id: the ID of the task to check

    :rtype: dict
    :returns:
        {
           'id': task_id,
           'status': one of PENDING, STARTED, RETRY, FAILURE, SUCCESS or a
                custom state,
            'info': any additional info for an incomplete task,
            'result': returned data from a SUCCESSFUL task,
            'error': returned exception from a FAILURE task,
            'data' : any addiitonal data we decide to add
        }
    """
    task_id = id  # We should decouple this
    async_call = app_or_default().AsyncResult(task_id)
    response = {'id': id, 'status': async_call.state}
    if async_call.ready():
        response['result'] = async_call.result
    else:
        if isinstance(async_call.info, BaseException):
            response['error'] = async_call.info.__str__()
        elif async_call.info and len(async_call.info):
            response['info'] = async_call.info.__str__()
    return response


@task
def distribute_deploy_plan(deployment, plan):
    """Taskes a YAML plan from CheckMate and executes it.

    :param deployment: contains the deployment parameters
    :type deployment: dict
    :param plan: the CheckMate plan
    :type plan: yaml
    """
    pass


@task
def count_seconds(seconds):
    """ just for debugging ansd testing long-running tasks and updates """
    elapsed = 0
    while elapsed < seconds:
        time.sleep(1)
        elapsed += 1
        count_seconds.update_state(state="PROGRESS",
                                   meta={'complete': elapsed,
                                         'total': seconds})
    return seconds


class Orchestrator(object):
    def __init__(self, deployment, auth):
        """ auth object is passed but not used yet. """
        self.deployment = deployment
        self.auth = auth
