""" Module to initialize the Checkmate REST API

REST API for Checkmate server

*****************************************************
*          This is still a VERY MESSY WIP           *
*****************************************************


Load these resources from their respective modules:
    /components:   juju charm-like definitions of services and components
    /environments: targets that can have resources deployed to them
    /blueprints:   *architect* definitions defining applications or solutions
    /deployments:  deployed resources (an instance of a blueprint deployed to
                   an environment)
    /workflows:    SpiffWorkflow workflows (persisted in database)

Special calls:
    POST /deployments/              This is where the meat of things gets done
                                    Triggers a celery task which can then be
                                    followed up on using deployments/:id/status
    GET  /deployments/:id/status    Check status of a deployment
    GET  /workflows/:id/status      Check status of a workflow
    GET  /workflows/:id/tasks/:id   Read a SpiffWorkflow Task
    POST /workflows/:id/tasks/:id   Partial update of a SpiffWorkflow Task
                                    Supports the following attributes: state,
                                    attributes, and internal_attributes
    GET  /workflows/:id/+execute    A browser-friendly way to run a workflow
    GET  /workflows/:id/tasks/:id/+reset   Reset a SpiffWorkflow Celery Task
    GET  /static/*                  Return files in /static folder
    PUT  /*/:id                     So you can edit/save objects without
                                    triggering actions (like a deployment).
                                    CAUTION: No locking or guarantees of
                                    atomicity across calls
Tools (added by this module):
    GET  /test/dump      Dumps the database
    POST /test/parse     Parses the body (use to test your yaml or json)
    POST /test/hack      Testing random stuff....
    GET  /test/async     Returns a streamed response (3 x 1 second intervals)

Notes:
    .yaml/.json extensions override Accept headers (except in /static/)
    Trailing slashes are ignored (ex. /blueprints/ == /blueprints)
"""
import logging
from subprocess import check_output
import sys

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

# pylint: disable=E0611
from bottle import get, request, response

from checkmate.utils import write_body

# Load modules containing APIs
# pylint: disable=W0611
from checkmate import blueprints, components, deployments, environments, \
    workflows


#
# Status and System Information
#
#@get('/status/celery')
def get_celery_worker_status():
    """ Checking on celery """
    ERROR_KEY = "ERROR"
    try:
        from celery.task.control import inspect
        insp = inspect()
        d = insp.stats()
        if not d:
            d = {ERROR_KEY: 'No running Celery workers were found.'}
    except IOError as e:
        from errno import errorcode
        msg = "Error connecting to the backend: " + str(e)
        if len(e.args) > 0 and errorcode.get(e.args[0]) == 'ECONNREFUSED':
            msg += ' Check that the RabbitMQ server is running.'
        d = {ERROR_KEY: msg}
    except ImportError as e:
        d = {ERROR_KEY: str(e)}
    return write_body(d, request, response)


@get('/status/libraries')
def get_dependency_versions():
    """ Checking on dependencies """
    result = {}
    libraries = [
                'bottle',  # HTTP request router
                'celery',  # asynchronous/queued call wrapper
                'Jinja2',  # templating library for HTML calls
                'kombu',   # message queue interface (dependency for celery)
                'openstack.compute',  # Rackspace CLoud Server (legacy) library
                'paramiko',  # SSH library
                'pycrypto',  # Cryptography (key generation)
                'python-novaclient',  # OpenStack Compute client library
                'python-clouddb',  # Rackspace DBaaS client library
                'pyyaml',  # YAML parser
                'SpiffWorkflow',  # Workflow Engine
                'sqlalchemy',  # ORM
                'sqlalchemy-migrate',  # database schema versioning
                'webob',   # HTTP request handling
                ]  # copied from setup.py with additions added
    for library in libraries:
        result[library] = {}
        try:
            if library in sys.modules:
                module = sys.modules[library]
                if hasattr(module, '__version__'):
                    result[library]['version'] = module.__version__
                result[library]['path'] = getattr(module, '__path__', 'N/A')
                result[library]['status'] = 'loaded'
            else:
                result[library]['status'] = 'not loaded'
        except Exception as exc:
            result[library]['status'] = 'ERROR: %s' % exc

    # Chef version
    try:
        output = check_output(['knife', '-v'])
        result['knife'] = {'version': output.strip()}
    except Exception as exc:
        result['knife'] = {'status': 'ERROR: %s' % exc}

    # Chef version
    expected = ['knife-solo',  'knife-solo_data_bag']
    try:
        output = check_output(['gem', 'list', 'knife-solo'])

        if output:
            for line in output.split('\n'):
                for name in expected[:]:
                    if line.startswith('%s ' % name):
                        output = line
                        result[name] = {'version': output.strip()}
                        expected.remove(name)
        for name in expected:
            result[name] = {'status': 'missing'}
    except Exception as exc:
        for name in expected:
            result[name] = {'status': 'ERROR: %s' % exc}

    return write_body(result, request, response)
