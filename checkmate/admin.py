"""

Module to initialize the Checkmate REST Admin API

This module load the /admin/* routes. It validates that all calls are performed
by a user with an admin context. It is optionally loadable (as determined by
server.py based on the --with-admin argument)

"""
import logging
from subprocess import check_output
import sys
import urlparse

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from bottle import get, request, response, abort

from checkmate import utils, db

__version_string__ = None
DB = db.get_driver()


def only_admins(fn):
    """ Decorator to limit access to admins only """
    def wrapped(*args, **kwargs):
        if request.context.is_admin == True:
            LOG.debug("Admin account '%s' accessing '%s'" %
                      (request.context.username, request.path))
            return fn(*args, **kwargs)
        else:
            abort(403, "Administrator privileges needed for this "
                  "operation")
    return wrapped


#
# Status and System Information
#
@get('/admin/status/celery')
@only_admins
def get_celery_worker_status():
    """ Checking on celery """
    ERROR_KEY = "ERROR"
    try:
        from celery.task.control import inspect
        insp = inspect()
        stats = insp.stats()
        if not stats:
            stats = {ERROR_KEY: 'No running Celery workers were found.'}
        else:
            # Sanitize it - remove passwords from URLs
            for key, worker in stats.iteritems():
                try:
                    url = worker['consumer']['broker']['hostname']
                    parsed = urlparse.urlparse(url)
                    url = url.replace(parsed.password, '*****')
                    worker['consumer']['broker']['hostname'] = url
                except:
                    pass
                try:
                    url = worker['consumer']['broker']['hostname']
                    if '@' in url and '*****' not in url:
                        url = "*****@%s" % url[url.index('@') + 1:]
                    worker['consumer']['broker']['hostname'] = url
                except:
                    pass
    except IOError as exc:
        from errno import errorcode
        msg = "Error connecting to the backend: " + str(exc)
        if len(exc.args) > 0 and errorcode.get(exc.args[0]) == 'ECONNREFUSED':
            msg += ' Check that the RabbitMQ server is running.'
        stats = {ERROR_KEY: msg}
    except ImportError as exc:
        stats = {ERROR_KEY: str(exc)}
    return utils.write_body(stats, request, response)


@get('/admin/status/libraries')
@only_admins
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

    return utils.write_body(result, request, response)


#
# Deployments
#
@get('/admin/deployments')
@utils.formatted_response('deployments', with_pagination=True)
def get_deployments(tenant_id=None, offset=None, limit=None, driver=DB):
    """ Get existing deployments """
    show_deleted = request.query.get('show_deleted')
    tenant_id = request.query.get('tenant_id')
    data = driver.get_deployments(
        tenant_id=tenant_id,
        offset=offset,
        limit=limit,
        with_deleted=show_deleted == '1'
    )
    return data
