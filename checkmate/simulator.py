""" Simulator for workflow processing

NOTE: FOR LOCAL DEVELOPMENT USE ONLY.

This module is enabled from server.py when the server is started with a
--with-simulator parameter

To use this, submit a deployment to /deployments/simulate and then
query it's state in /workflows/simulate. Each GET will progress one task
at a time.
"""

# pylint: disable=E0611
import json
import logging
import os
from time import sleep
import uuid

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
from checkmate.workflows import get_SpiffWorkflow_status, create_workflow_deploy
from checkmate.utils import write_body, read_body, with_tenant

PACKAGE = {}
LOG = logging.getLogger(__name__)


#
# Making life easy - calls that are handy but should not be in final API
#
@post('/test/parse')
def parse():
    """ For debugging only """
    return write_body(read_body(request), request, response)


@post('/test/hack')
def hack():
    """ Use it to test random stuff """
    entity = read_body(request)
    if 'deployment' in entity:
        entity = entity['deployment']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        abort(406, any_id_problems(entity['id']))

    dep = Deployment(entity)
    plan(dep, request.context)

    wf = create_workflow_deploy(dep, request.context)

    serializer = DictionarySerializer()
    data = serializer._serialize_task_spec(
             wf.spec.task_specs['Collect apache2 Chef Data: 4'])

    return write_body(data, request, response)


@get('/test/async')
def async():
    """Test async responses"""
    response.set_header('content-type', "application/json")
    response.set_header('Location', "uri://something")

    def afunc():
        yield ('{"Note": "To watch this in real-time, run: curl '\
                'http://localhost:8080/test/async -N -v",')
        sleep(1)
        for i in range(3):
            yield '"%i": "Counting",' % i
            sleep(1)
        yield '"Done": 3}'
    return afunc()

#
# Simulator
#

@post('/deployments/simulate')
@with_tenant
def simulate(tenant_id=None):
    """ Run a simulation """
    global PACKAGE
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

    PACKAGE[tenant_id] = deployment
    results = plan(deployment, request.context)
    PACKAGE[tenant_id] = results

    serializer = DictionarySerializer()
    workflow = create_workflow_deploy(deployment, request.context)
    serialized_workflow = workflow.serialize(serializer)
    results['workflow'] = serialized_workflow
    results['workflow']['id'] = 'simulate'
    PACKAGE[tenant_id] = results

    return write_body(results, request, response)


@get('/deployments/simulate')
@with_tenant
def display(tenant_id=None):
    global PACKAGE
    if not PACKAGE.get(tenant_id):
        abort(404, "No simulated deployment exists for %s" % tenant_id)
    return write_body(PACKAGE[tenant_id], request, response)


@get('/workflows/simulate')
@with_tenant
def workflow_state(tenant_id=None):
    """Return slightly updated workflow each time"""
    global PACKAGE
    if not PACKAGE.get(tenant_id):
        abort(404, "No simulated deployment exists for %s" % tenant_id)

    results = process(tenant_id)

    return write_body(results, request, response)


@get('/workflows/simulate/status')
@with_tenant
def workflow_status(tenant_id=None):
    """Return simulated workflow status"""
    global PACKAGE
    if not PACKAGE.get(tenant_id):
        abort(404, "No simulated deployment exists")

    result = workflow_state(tenant_id)  # progress and return workflow
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
    global PACKAGE
    if not PACKAGE.get(tenant_id):
        abort(404, "No simulated deployment exists for %s" % tenant_id)

    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, PACKAGE[tenant_id]['workflow'])

    task = wf.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)
    data = serializer._serialize_task(task, skip_children=True)
    data['workflow_id'] = 'simulate'  # so we know which workflow it came from
    return write_body(data, request, response)


def process(tenant_id):
    """Process one task at a time. Patch Celery class to not make real calls"""
    path = os.path.normpath(os.path.join(os.path.dirname(__file__),
                                         'simulator.json'))
    serializer = DictionarySerializer()
    with open(path) as f:
        data = json.load(f)
        template = Workflow.deserialize(serializer, data)

    global PACKAGE
    if 'workflow' not in PACKAGE[tenant_id]:
        abort(404, "Workflow does not exist")
    workflow = Workflow.deserialize(serializer, PACKAGE[tenant_id]['workflow'])

    def hijacked_try_fire(self, my_task, force=False):
        """We patch this in to intercept calls that would go to celery"""
        name = my_task.get_name()
        result = None
        if name in template.spec.task_specs:
            template_task = None  # template.get_task(my_task.id)
            for task in template.get_tasks():
                if task.get_name() == name:
                    template_task = task
                    break
            if template_task:
                result = template_task.attributes
            else:
                LOG.warn("Task not found in simulator.json: %s" % name)
        else:
            LOG.warn("Spec not found in simulator.json: %s" % name)
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
                    PACKAGE[tenant_id].on_resource_postback(data)
        return True

    try_fire = Celery.try_fire
    try:
        Celery.try_fire = hijacked_try_fire
        workflow.complete_next()
    finally:
        Celery.try_fire = try_fire

    results = workflow.serialize(serializer)
    results['id'] = 'simulate'
    PACKAGE[tenant_id]['workflow'] = results
    return results
