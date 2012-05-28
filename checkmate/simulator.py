""" Simulator for workflow processing

NOTE: FOR LOCAL DEVELOPMENT USE ONLY.

To use this, submit a deployment to /deployments/simulate and then
query it's state in /workflows/simulate. Each GET will progress one task
at a time.
"""

# pylint: disable=E0611
from bottle import get, post, request, response, abort
import json
import logging
import os
import sys
import time

try:
    from SpiffWorkflow.specs import WorkflowSpec, Celery, Transform, Merge
except ImportError:
    #TODO(zns): remove this when Spiff incorporates the code in it
    print "Get SpiffWorkflow with the Celery spec in it from here: "\
            "https://github.com/ziadsawalha/SpiffWorkflow/tree/celery"
    raise

from SpiffWorkflow import Workflow
from SpiffWorkflow.storage import DictionarySerializer

from checkmate.db import any_id_problems
from checkmate.utils import write_body, read_body
from checkmate.deployments import plan_dict
from checkmate.workflows import get_SpiffWorkflow_status

# Import these for simulation only so that bottle knows to reload when we edit
# them
from checkmate.providers.rackspace import compute, legacy, loadbalancer,\
        database
from checkmate.providers.opscode import chef_local, chef_server

PHASE = time.time()
PACKAGE = None

LOG = logging.getLogger(__name__)


@post('/deployments/simulate')
@post('/<tenant_id>/deployments/simulate')
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

    response.add_header('Location', "/deployments/simulate")

    results = plan_dict(entity)

    serializer = DictionarySerializer()
    workflow = results['workflow'].serialize(serializer)
    results['workflow'] = workflow
    results['workflow']['id'] = 'simulate'
    PACKAGE = results

    return write_body(results, request, response)


@get('/deployments/simulate')
@get('/<tenant_id>/deployments/simulate')
def display(tenant_id=None):
    global PHASE, PACKAGE
    return write_body(PACKAGE, request, response)


@get('/workflows/simulate')
@get('/<tenant_id>/workflows/simulate')
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
@get('/<tenant_id>/workflows/simulate/tasks/<task_id:int>')
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
        responses = json.load(f)
        template = Workflow.deserialize(serializer, responses['workflow'])

    global PHASE, PACKAGE
    workflow = Workflow.deserialize(serializer, PACKAGE['workflow'])

    def hijacked_try_fire(self, my_task, force=False):
        """We patch this in to intercept calls that would go to celery"""
        celery_module = sys.modules['SpiffWorkflow.specs.Celery']
        if self.args:
            args = celery_module.eval_args(self.args, my_task)
            if self.kwargs:
                LOG.debug("Hijacked %s(%s, %s)" % (self.call, args,
                        celery_module.eval_kwargs(self.kwargs, my_task)))
            else:
                LOG.debug("Hijacked %s(%s)" % (self.call, args))
        else:
            if self.kwargs:
                LOG.debug("Hijacked %s(%s, %s)" % (self.call,
                        celery_module.eval_kwargs(self.kwargs, my_task)))
            else:
                LOG.debug("Hijacked %s(%s, %s)" % (self.call))
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
