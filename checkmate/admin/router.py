"""

Module to initialize the Checkmate REST Admin API

This module load the /admin/* routes. It validates that all calls are performed
by a user with an admin context. It is optionally loadable (as determined by
server.py based on the --with-admin argument)

Supports:
PUT /admin/tenants
GET /admin/tenants/tenant_id
GET /admin/tenants/ and return all
GET /admin/tenants?tag=foo&tag=bar

"""
import logging
from subprocess import check_output
import sys
import urlparse

from bottle import request, response

from checkmate import utils

LOG = logging.getLogger(__name__)


class Router(object):
    '''Route /admin/ calls'''

    def __init__(self, app, manager, tenant_manager):
        '''Takes a bottle app and routes traffic for it'''
        self.app = app
        self.manager = manager
        self.tenant_manager = tenant_manager

        app.route('/admin/status/celery', 'GET', self.get_celery_worker_status)
        app.route('/admin/status/libraries', 'GET',
                  self.get_dependency_versions)
        app.route('/admin/deployments', 'GET', self.get_deployments)
        app.route('/admin/deployments/count', 'GET',
                  self.get_deployment_count)
        app.route('/admin/deployments/count/<blueprint_id>', 'GET',
                  self.get_deployment_count_by_bp)

        app.route('/admin/tenants', 'GET', self.get_tenants)
        app.route('/admin/tenants/<tenant_id>', 'GET', self.get_tenant)
        app.route('/admin/tenants/<tenant_id>', 'PUT', self.put_tenant)
        app.route('/admin/tenants/<tenant_id>', 'POST', self.add_tenant_tags)

    #
    # Status and System Information
    #
    @utils.only_admins
    def get_celery_worker_status(self):
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
                    except StandardError:
                        pass
                    try:
                        url = worker['consumer']['broker']['hostname']
                        if '@' in url and '*****' not in url:
                            url = "*****@%s" % url[url.index('@') + 1:]
                        worker['consumer']['broker']['hostname'] = url
                    except StandardError:
                        pass
        except IOError as exc:
            from errno import errorcode
            msg = "Error connecting to the backend: " + str(exc)
            if len(exc.args) > 0 and \
                    errorcode.get(exc.args[0]) == 'ECONNREFUSED':
                msg += ' Check that the RabbitMQ server is running.'
            stats = {ERROR_KEY: msg}
        except ImportError as exc:
            stats = {ERROR_KEY: str(exc)}
        return utils.write_body(stats, request, response)

    @utils.only_admins
    def get_dependency_versions(self):
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
                    result[library]['path'] = getattr(module, '__path__',
                                                      'N/A')
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
        expected = ['knife-solo', 'knife-solo_data_bag']
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
    @utils.only_admins
    @utils.formatted_response('deployments', with_pagination=True)
    def get_deployments(self, tenant_id=None, offset=None, limit=None):
        """ Get existing deployments """
        show_deleted = request.query.get('show_deleted')
        status = request.query.get('status')
        tenant_id = request.query.get('tenant_id')
        data = self.manager.get_deployments(
            tenant_id=tenant_id,
            offset=offset,
            limit=limit,
            with_deleted=show_deleted == '1',
            status=status,
        )
        return data

    @utils.only_admins
    def get_deployment_count(self):
        '''
        Get the number of deployments. May limit response to include all
        deployments for a particular tenant and/or blueprint

        :param:tenant_id: the (optional) tenant
        '''
        tenant_id = request.query.get('tenant_id')
        status = request.query.get('status')
        count = self.manager.count(tenant_id=tenant_id, status=status)
        return utils.write_body({"count": count}, request, response)

    @utils.only_admins
    def get_deployment_count_by_bp(self, blueprint_id):
        '''
        Return the number of times the given blueprint appears
        in saved deployments

        :param:blueprint_id: the blueprint ID
        :param:tenant_id: the (optional) tenant
        '''
        tenant_id = request.query.get('tenant_id')
        count = self.manager.count(tenant_id=tenant_id,
                                   blueprint_id=blueprint_id)
        return utils.write_body({'count': count}, request, response)

    #
    # Tenants
    #
    @utils.only_admins
    @utils.formatted_response('tenants', with_pagination=False)
    def get_tenants(self):
        return self.tenant_manager.list_tenants(*request.query.getall('tag'))

    @utils.only_admins
    def put_tenant(self, tenant_id):
        ten = {}
        if request.content_length > 0:
            ten = utils.read_body(request)
        self.tenant_manager.save_tenant(tenant_id, ten)
        response.status = 201

    @utils.only_admins
    def get_tenant(self, tenant_id):
        if tenant_id:
            tenant = self.tenant_manager.get_tenant(tenant_id)
            return utils.write_body(tenant, request, response)

    @utils.only_admins
    def add_tenant_tags(self, tenant_id):
        if tenant_id:
            body = utils.read_body(request)
            new = body.get('tags')
            if new and not isinstance(new, (list, tuple)):
                new = [new]
            self.tenant_manager.add_tenant_tags(tenant_id, *new)
            response.status = 204
