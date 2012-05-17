""" Simulator for workflow processing

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

PHASE = time.time()
PACKAGE = None

LOG = logging.getLogger(__name__)


@post('/deployments/simulate')
def simulate():
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
    PACKAGE = results

    return write_body(results, request, response)


@get('/deployments/simulate')
def display():
    global PHASE, PACKAGE
    return write_body(PACKAGE, request, response)


@get('/workflows/simulate')
def workflow_state():
    """Return slightly updated workflow each time"""
    global PHASE

    results = process()

    return write_body(results, request, response)


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
    PACKAGE['workflow'] = results
    return results
