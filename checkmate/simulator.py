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
from SpiffWorkflow.operators import Attrib, PathAttrib, valueof
from SpiffWorkflow.specs import TransMerge
from SpiffWorkflow.storage import DictionarySerializer

from checkmate.db import any_id_problems
from checkmate.deployments import plan, Deployment
from checkmate.workflows import (get_SpiffWorkflow_status,
                                 create_workflow_deploy)
from checkmate.utils import (write_body, read_body, with_tenant,
                             merge_dictionary)

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
        response.add_header('Link', '</%s/deployments/simulate>; '
                            'rel="workflow"; title="Deploy"' % tenant_id)
    else:
        response.add_header('Location', "/deployments/simulate")
        response.add_header('Link', '</deployments/simulate>; rel="workflow"; '
                            'title="Deploy"')

    PACKAGE[tenant_id] = {'deployment': deployment}
    results = plan(deployment, request.context)
    PACKAGE[tenant_id]['deployment'] = results

    serializer = DictionarySerializer()
    workflow = create_workflow_deploy(deployment, request.context)

    # Hack to hijack postback in Transform which is called as a string in
    # exec(), so cannot be easily mocked.
    # We make the call hit our deployment directly
    call_me = 'dep.on_resource_postback(output_template) #'
    for spec in workflow.spec.task_specs.values():
        if (isinstance(spec, TransMerge) and
                'postback.' in spec.transforms[0]):
            stub = spec.transforms[0].replace('postback.', call_me)
            spec.transforms[0] = stub

    serialized_workflow = workflow.serialize(serializer)
    results['workflow'] = 'simulate'
    PACKAGE[tenant_id]['workflow'] = serialized_workflow

    return write_body(results, request, response)


@get('/deployments/simulate')
@with_tenant
def display(tenant_id=None):
    global PACKAGE
    if not PACKAGE.get(tenant_id):
        abort(404, "No simulated deployment exists for %s" % tenant_id)
    return write_body(PACKAGE[tenant_id]['deployment'], request, response)


@get('/workflows/simulate')
@with_tenant
def workflow_state(tenant_id=None):
    """Return slightly updated workflow each time"""
    global PACKAGE
    if not PACKAGE.get(tenant_id):
        abort(404, "No simulated deployment exists for %s" % tenant_id)

    complete = 'complete' in request.query
    results = process(tenant_id, complete=complete)

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


def process(tenant_id, complete=False):
    """

    Process simulated deployment and workflow.

    :param tenant_id: simulated objects are stored per tenant in memoty. We
                      need this key to find the right one.
    :param complete: set this to true to complete the workflow. Otherwsie, each
                     call moves it ahead by only one call
    Note: Patches Celery class to not make real calls

    """
    global PACKAGE
    if 'workflow' not in PACKAGE[tenant_id]:
        abort(404, "Workflow does not exist")
    serializer = DictionarySerializer()
    workflow = Workflow.deserialize(serializer, PACKAGE[tenant_id]['workflow'])

    def hijacked_try_fire(self, my_task, force=False):
        """We patch this in to intercept calls that would go to celery"""
        result = simulate_result(tenant_id, my_task, workflow)
        if result:
            # From Celery.try_file
            if self.result_key:
                data = {self.result_key: result}
            else:
                if isinstance(result, dict):
                    data = result
                else:
                    data = {'result': result}
            # Load formatted result into attributes
            if self.merge_results:
                merge_dictionary(my_task.attributes, data)
            else:
                my_task.set_attribute(**data)

            # Post-back instance and connection data
            postback = {}
            for k, v in data.iteritems():
                if k.startswith('instance:'):
                    postback[k] = v
                elif k.startswith('connection:'):
                    postback[k] = v
            if postback:
                PACKAGE[tenant_id]['deployment'].on_resource_postback(postback)
        return True

    # Hack to hijack postback in Transform which is called as a string in
    # exec(), so cannot be easily mocked.
    # We make the call hit our deployment directly
    # TODO: remove hack
    call_me = 'dep.on_resource_postback(output_template) #'
    deployment = Deployment(PACKAGE[tenant_id]['deployment'])
    for spec in workflow.spec.task_specs.values():
        if (isinstance(spec, TransMerge) and
                call_me in spec.transforms[0]):
            spec.set_property(deployment=deployment)
    # End Hack

    try_fire = Celery.try_fire
    try:
        Celery.try_fire = hijacked_try_fire
        if complete is True:
            workflow.complete_all()
        else:
            workflow.complete_next()
    finally:
        Celery.try_fire = try_fire

    # Hack to hijack postback in Transform
    # Remove the deployment reference since it cannot be serialized
    # TODO: remove hack
    call_me = 'dep.on_resource_postback(output_template) #'
    for spec in workflow.spec.task_specs.values():
        if (isinstance(spec, TransMerge) and
                call_me in spec.transforms[0]):
            del spec.properties['deployment']
    # End Hack

    results = workflow.serialize(serializer)
    results['id'] = 'simulate'
    PACKAGE[tenant_id]['workflow'] = results
    return results


# Copied from SpiffWorkflow.spec.Celery because they can't be accessed
def eval_args(args, my_task):
    """Parses args and evaluates any Attrib entries"""
    results = []
    for arg in args:
        if isinstance(arg, Attrib) or isinstance(arg, PathAttrib):
            results.append(valueof(my_task, arg))
        else:
            results.append(arg)
    return results


def eval_kwargs(kwargs, my_task):
    """Parses kwargs and evaluates any Attrib entries"""
    results = {}
    for kwarg, value in kwargs.iteritems():
        if isinstance(value, Attrib) or isinstance(value, PathAttrib):
            results[kwarg] = valueof(my_task, value)
        else:
            results[kwarg] = value
    return results


def simulate_result(tenant_id, my_task, workflow):
    """Simulate result data based on provider, deployment, and workflow"""
    global PACKAGE
    spec = my_task.task_spec
    props = spec.properties
    resource = None
    result = None
    call = getattr(spec, 'call', None)
    provider = props.get('provider')
    deployment = PACKAGE[tenant_id]['deployment']
    arg, kwargs = None, None
    if spec.args:
        args = eval_args(spec.args, my_task)
    if spec.kwargs:
        kwargs = eval_kwargs(spec.kwargs, my_task)

    if 'resource' in props:
        resource_key = props['resource']
        resource = deployment['resources'][resource_key]
    else:
        resource_key = None
        resource = {}
    if call in ["checkmate.providers.rackspace.compute.create_server",
                "checkmate.providers.rackspace.compute_legacy.create_server",
               ]:
        result = {
                  'instance:%s' % resource_key: {
                    'id': '200%s' % resource_key,
                    'password': "shecret",
                    }
                  }
    elif call in ["checkmate.providers.rackspace.compute.wait_on_build",
                  "checkmate.providers.rackspace.compute_legacy."
                        "wait_on_build",
                 ]:
        result = {
                'instance:%s' % resource_key: {
                    'status': "ACTIVE",
                    'ip': '4.4.4.%s' % resource_key,
                    'public_ip': '4.4.4.%s' % resource_key,
                    'private_ip': '10.1.2.%s' % resource_key,
                    'addresses': {
                      'public': [
                        {
                          "version": 4,
                          "addr": "4.4.4.%s" % resource_key,
                        },
                        {
                          "version": 6,
                          "addr": "2001:babe::ff04:36c%s" % resource_key,
                        }
                      ],
                      'private': [
                        {
                          "version": 4,
                          "addr": "10.1.2.%s" % resource_key,
                        }
                      ]
                    }
                }
            }
    elif call == ("checkmate.providers.rackspace.loadbalancer."
                       "create_loadbalancer"):
        result = {
                  'instance:%s' % resource_key: {
                        'id': "LB0%s" % resource_key,
                        'public_ip': "4.4.4.20%s" % resource_key,
                        'port': "dummy",
                        'protocol': "dummy"}}
    elif call in ["checkmate.providers.rackspace.database.create_database",
                  ]:
        instance_id = kwargs.get('instance_id', 'DBS%s' % resource_key)
        hostname = "srv%s.rackdb.net" % resource_key
        database_name = args[1]
        result = {
                'instance:%s' % resource_key: {
                        'name': database_name,
                        'host_instance': instance_id,
                        'host_region': resource.get('region'),
                        'interfaces': {
                                'mysql': {
                                        'host': hostname,
                                        'database_name': database_name
                                    },
                            }
                    }
            }
    elif call in ["checkmate.providers.rackspace.database.create_instance",
                  ]:
        result = {
            'instance:%s' % resource_key: {
                    'id': "DBS%s" % resource_key,
                    'name': resource['dns-name'],
                    'status': "ACTIVE",
                    'region': resource.get('region'),
                    'interfaces': {
                            'mysql': {
                                    'host': "srv%s.rackdb.net" % resource_key
                                }
                        },
                    'databases': {}
                }
        }
    elif call in ["checkmate.providers.opscode.knife.cook",
                  ]:
        if my_task.attributes:
            # Take output from map and post it back
            result = my_task.attributes.get('instance:%s' % resource_key, {})
            if result:
                result = {'instance:%s' % resource_key: result}
        else:
            result = {}
        if not result:
            LOG.debug("Ignoring task '%s' for provider '%s' in simuator" %
                      (provider, spec.name))
    elif call in ["checkmate.providers.opscode.knife.write_databag",
                  "checkmate.providers.opscode.knife.write_role",
                  ]:
        result = {}
        LOG.debug("Ignoring task '%s' for provider '%s' in simuator" %
                  (provider, spec.name))
    elif provider == 'chef-solo':
        if props.get('relation') == 'host':
            result = {}
            LOG.debug("Ignoring task '%s' for provider '%s' in simuator" %
                      (provider, spec.name))
        elif 'root' in props.get('task_tags', []):
            result = {
                'environment': '/var/tmp/%s/' % deployment['id'],
                'kitchen': '/var/tmp/%s/kitchen' % deployment['id'],
                'private_key_path': '/var/tmp/%s/private.pem' %
                        deployment['id'],
                'public_key_path': '/var/tmp/%s/checkmate.pub' %
                        deployment['id']}
        elif ('task_tags' in props and (
                'final' in props['task_tags'] or
                'options-ready' in props['task_tags'])):
            result = {}
            LOG.debug("Ignoring task '%s' for provider '%s' in simuator" %
                      (provider, spec.name))
    elif provider == 'load-balancer':
        if 'final' in props.get('task_tags', []):
            result = {}
            LOG.debug("Ignoring task '%s' for provider '%s' in simuator" %
                      (provider, spec.name))


    if result is None:
        LOG.info("Consider handling a simulated result for task '%s'. The "
                 "resource is %s and the spec properties are %s" % (
                 spec.name, resource, props))
    return result
