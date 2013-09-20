# Copyright (c) 2011-2013 Rackspace Hosting
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Module to initialize the Checkmate REST Admin API

This module load the /admin/* routes. It validates that all calls are performed
by a user with an admin context. It is optionally loadable (as determined by
server.py based on the --with-admin argument)

Supports:
PUT /admin/tenants
GET /admin/tenants/tenant_id
GET /admin/tenants/ and return all
GET /admin/tenants?tag=foo&tag=bar
"""

import copy
import errno
import logging
import subprocess
import sys
import urlparse

import bottle

from checkmate import utils

LOG = logging.getLogger(__name__)


class Router(object):
    """Route /admin/ calls."""

    def __init__(self, app, deployments_manager, tenants_manager):
        """Takes a bottle app and routes traffic for it.

        :param app: bottle application to route to
        :param deployments_manager: for /admin/deployments calls
        :param tenants_manager: for /admin/tenants calls
        """
        self.app = app
        self.deployments_manager = deployments_manager
        self.tenants_manager = tenants_manager

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

        #app.route('/admin/cache/blueprints', 'GET', self.get_cached_blueprints)

    #
    # Status and System Information
    #
    @staticmethod
    @utils.only_admins
    def get_celery_worker_status():
        """Checking on celery."""
        error_key = "ERROR"
        try:
            from celery.task import control
            insp = control.inspect()
            stats = insp.stats()
            if not stats:
                stats = {error_key: 'No running Celery workers were found.'}
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
            msg = "Error connecting to the backend: " + str(exc)
            if len(exc.args) > 0 and \
                    errno.errorcode.get(exc.args[0]) == 'ECONNREFUSED':
                msg += ' Check that the RabbitMQ server is running.'
            stats = {error_key: msg}
        except ImportError as exc:
            stats = {error_key: str(exc)}
        return utils.write_body(stats, bottle.request, bottle.response)

    @staticmethod
    @utils.only_admins
    def get_dependency_versions():
        """Checking on dependencies."""
        result = {}
        libraries = [
            'bottle',  # HTTP request router
            'celery',  # asynchronous/queued call wrapper
            'Jinja2',  # templating library for HTML calls
            'kombu',   # message queue interface (dependency for celery)
            'openstack.compute',  # Rackspace CLoud Server (legacy) library
            'paramiko',  # SSH library
            'pycrypto',  # Cryptography (key generation)
            'pyrax',  # Python Rackspace Cloud bindings
            'python-novaclient',  # OpenStack Compute client library
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
            output = subprocess.check_output(['knife', '-v'])
            result['knife'] = {'version': output.strip()}
        except Exception as exc:
            result['knife'] = {'status': 'ERROR: %s' % exc}

        # Chef version
        expected = ['knife-solo', 'knife-solo_data_bag']
        try:
            output = subprocess.check_output(['gem', 'list', 'knife-solo'])

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

        return utils.write_body(result, bottle.request, bottle.response)

    #
    # Deployments
    #
    param_whitelist = ['search', 'name', 'blueprint.name', 'tenantId',
                       'status', 'start_date', 'end_date', 'created-by',
                       'environment.providers.chef-solo.constraints.source']

    @utils.only_admins
    @utils.formatted_response('deployments', with_pagination=True)
    def get_deployments(self, tenant_id=None, offset=None, limit=None):
        """Get existing deployments."""
        limit = utils.cap_limit(limit, tenant_id)  # Avoid DoS from huge limit
        show_deleted = bottle.request.query.get('show_deleted')
        statuses = bottle.request.query.get('status')
        tenant_id = bottle.request.query.get('tenant_id')
        params = copy.deepcopy(bottle.request.query.dict)

        if 'tenant_tag' in params:
            tags = params['tenant_tag']
            tenants = self.tenants_manager.list_tenants(*tags)
            if len(tenants) == 0:
                tenants['no-tenants-found'] = True
            params['tenantId'] = tenants.keys()
            params.pop('tenant_tag')
        if 'blueprint_branch' in params:
            attr = 'environment.providers.chef-solo.constraints.source'
            params[attr] = map(
                lambda x: '%#' + x, params.pop('blueprint_branch'))

        query = utils.QueryParams.parse(params, self.param_whitelist)

        return self.deployments_manager.get_deployments(
            tenant_id=tenant_id,
            offset=offset,
            limit=limit,
            with_deleted=show_deleted == '1',
            status=statuses,
            query=query,
        )

    @utils.only_admins
    def get_deployment_count(self):
        """Get the number of deployments.

        May limit response to include all
        deployments for a particular tenant and/or blueprint

        :param:tenant_id: the (optional) tenant
        """
        tenant_id = bottle.request.query.get('tenant_id')
        status = bottle.request.query.get('status')
        params = bottle.request.query.dict
        query = utils.QueryParams.parse(params, self.param_whitelist)
        count = self.deployments_manager.count(tenant_id=tenant_id,
                                               status=status,
                                               query=query
                                               )
        result = {'count': count}
        return utils.write_body(result, bottle.request, bottle.response)

    @utils.only_admins
    def get_deployment_count_by_bp(self, blueprint_id):
        """Return the number of times the given blueprint appears
        in saved deployments.

        :param:blueprint_id: the blueprint ID
        :param:tenant_id: the (optional) tenant
        """
        tenant_id = bottle.request.query.get('tenant_id')
        count = self.deployments_manager.count(tenant_id=tenant_id,
                                               blueprint_id=blueprint_id)
        result = {'count': count}
        return utils.write_body(result, bottle.request, bottle.response)

    #
    # Tenants
    #
    @utils.only_admins
    @utils.formatted_response('tenants', with_pagination=False)
    def get_tenants(self):
        """Return the list of tenants."""
        return self.tenants_manager.list_tenants(
            *bottle.request.query.getall('tag'))

    @utils.only_admins
    def put_tenant(self, tenant_id):
        """Save a whole tenant."""
        ten = {}
        if bottle.request.content_length > 0:
            ten = utils.read_body(bottle.request)
        self.tenants_manager.save_tenant(tenant_id, ten)
        bottle.response.status = 201

    @utils.only_admins
    def get_tenant(self, tenant_id):
        """Return a requested tenant by id."""
        if tenant_id:
            tenant = self.tenants_manager.get_tenant(tenant_id)
            return utils.write_body(tenant, bottle.request, bottle.response)

    @utils.only_admins
    def add_tenant_tags(self, tenant_id):
        """Update tenant tags."""
        if tenant_id:
            body = utils.read_body(bottle.request)
            new = body.get('tags')
            if new and not isinstance(new, (list, tuple)):
                new = [new]
            self.tenants_manager.add_tenant_tags(tenant_id, *new)
            bottle.response.status = 204
