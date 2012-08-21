""" Simulator for workflow processing

NOTE: FOR LOCAL DEVELOPMENT USE ONLY.

To use this, submit a deployment to /deployments/simulate and then
query it's state in /workflows/simulate. Each GET will progress one task
at a time.
"""

# pylint: disable=E0611
import json
import logging
import os
import time

from bottle import get, post, request, response, abort
try:
    from SpiffWorkflow.specs import Celery
except ImportError:
    #TODO(zns): remove this when Spiff incorporates the code in it
    print "Get SpiffWorkflow with the Celery spec in it from here: "\
            "https://github.com/ziadsawalha/SpiffWorkflow/"
    raise

from SpiffWorkflow import Workflow
from SpiffWorkflow.storage import DictionarySerializer

from checkmate.common import schema
from checkmate.db import any_id_problems
from checkmate.deployments import plan, Deployment
from checkmate.workflows import get_SpiffWorkflow_status, create_workflow
from checkmate.utils import write_body, read_body, with_tenant


PHASE = time.time()
PACKAGE = None

LOG = logging.getLogger(__name__)


@post('/deployments/simulate')
@with_tenant
def simulate(tenant_id=None):
    """ Run a simulation """
    global PHASE, PACKAGE
    PHASE = time.time()
    entity = read_body(request)
    if 'deployment' in entity:
        entity = entity['deployment']

    if 'id' not in entity:
        entity['id'] = "simulate"
    if any_id_problems(entity['id']):
        abort(406, any_id_problems(entity['id']))

    deployment = Deployment(entity)
    if 'includes' in deployment:
        del deployment['includes']

    if tenant_id:
        response.add_header('Location', "/%s/deployments/simulate" % tenant_id)
    else:
        response.add_header('Location', "/deployments/simulate")

    PACKAGE = deployment
    results = plan(deployment, request.context)
    PACKAGE = results

    serializer = DictionarySerializer()
    workflow = create_workflow(deployment, request.context)
    serialized_workflow = workflow.serialize(serializer)
    results['workflow'] = serialized_workflow
    results['workflow']['id'] = 'simulate'
    PACKAGE = results

    return write_body(results, request, response)


@get('/deployments/simulate')
@with_tenant
def display(tenant_id=None):
    global PHASE, PACKAGE
    return write_body(PACKAGE, request, response)


@get('/workflows/simulate')
@with_tenant
def workflow_state(tenant_id=None):
    """Return slightly updated workflow each time"""
    global PHASE

    results = process()

    return write_body(results, request, response)


@get('/workflows/simulate/status')
def workflow_status():
    """Return simulated workflow status"""
    global PHASE

    result = workflow_state()  # progress and return workflow
    entity = json.loads(result)

    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, entity)
    return write_body(get_SpiffWorkflow_status(wf), request, response)


@get('/workflows/simulate/tasks/<task_id:int>')
@with_tenant
def get_workflow_task(task_id, tenant_id=None):
    """Get a workflow task

    :param task_id: checkmate workflow task id
    """
    global PHASE

    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, PACKAGE['workflow'])

    task = wf.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)
    data = serializer._serialize_task(task, skip_children=True)
    data['workflow_id'] = 'simulate'  # so we know which workflow it came from
    return write_body(data, request, response)


def process():
    """Process one task at a time. Patch Celery class to not make real calls"""
    path = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir,
            'tests', 'data', 'simulator.json'))
    serializer = DictionarySerializer()
    with open(path) as f:
        data = json.load(f)
        template = Workflow.deserialize(serializer, data)

    global PHASE, PACKAGE
    workflow = Workflow.deserialize(serializer, PACKAGE['workflow'])

    def hijacked_try_fire(self, my_task, force=False):
        """We patch this in to intercept calls that would go to celery"""
        name = my_task.get_name()
        result = None
        if name in template.spec.task_specs:
            template_task = template.get_task(my_task.id)
            for task in template.get_tasks():
                if task.get_name() == name:
                    template_task = task
                    break
            result = template_task.attributes
        else:
            LOG.warn("Unhandled task: %s" % name)
        if result:
            my_task.set_attribute(**result)
            if my_task.task_spec.call.startswith('checkmate.providers.'
                    'rackspace.'):
                data = {}
                for k, v in result.iteritems():
                    if k.startswith('instance:'):
                        data[k] = v
                    elif k.startswith('connection:'):
                        data[k] = v

                if data:
                    PACKAGE.on_resource_postback(data)
        return True

    try_fire = Celery.try_fire
    try:
        Celery.try_fire = hijacked_try_fire
        workflow.complete_next()
    finally:
        Celery.try_fire = try_fire

    results = workflow.serialize(serializer)
    results['id'] = 'simulate'
    PACKAGE['workflow'] = results
    return results
