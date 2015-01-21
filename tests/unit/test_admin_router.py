# pylint: disable=C0103,R0904

# Copyright (c) 2011-2015 Rackspace US, Inc.
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

"""Tests for Admin Router."""
import mock
import unittest
import webtest

import bottle

from checkmate import admin
from checkmate import exceptions
from checkmate import test


class TestAdminRouter(unittest.TestCase):

    deployments_manager = mock.Mock()
    tenant_manager = mock.Mock()
    blueprints_manager = mock.Mock()

    def setUp(self):
        """Sets up mocked router and webtest apps.

        Override class variables with custom managers if needed.
        """
        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.filters.context.is_admin = True
        self.app = webtest.TestApp(self.filters)
        self.router = admin.Router(self.root_app, self.deployments_manager,
                                   self.tenant_manager,
                                   blueprints_manager=self.blueprints_manager)

        results = {'_links': {}, 'results': {}, 'collection-count': 0}
        self.deployments_manager.get_deployments.return_value = results


class TestParamWhitelist(TestAdminRouter):

    def setUp(self):
        super(TestParamWhitelist, self).setUp()

    def test_there_are_9_items_being_whitelisted(self):
        num_params = len(admin.Router.param_whitelist)
        self.assertEqual(num_params, 9)

    def test_search_is_whitelisted(self):
        self.assertTrue('search' in admin.Router.param_whitelist)

    def test_name_is_whitelisted(self):
        self.assertTrue('name' in admin.Router.param_whitelist)

    def test_blueprint_name_is_whitelisted(self):
        self.assertTrue('blueprint.name' in admin.Router.param_whitelist)

    def test_tenantId_is_whitelisted(self):
        self.assertTrue('tenantId' in admin.Router.param_whitelist)

    def test_status_is_whitelisted(self):
        self.assertTrue('status' in admin.Router.param_whitelist)

    def test_start_date_is_whitelisted(self):
        self.assertTrue('start_date' in admin.Router.param_whitelist)

    def test_end_date_is_whitelisted(self):
        self.assertTrue('end_date' in admin.Router.param_whitelist)

    def test_created_by_is_whitelisted(self):
        self.assertTrue('created-by' in admin.Router.param_whitelist)

    def test_blueprint_source_is_whitelisted(self):
        self.assertTrue('environment.providers.chef-solo.constraints.source'
                        in admin.Router.param_whitelist)


class TestGetDeployments(TestAdminRouter):

    def setUp(self):
        super(TestGetDeployments, self).setUp()

    @mock.patch.object(admin.router.utils.QueryParams, 'parse')
    def test_pass_query_params_to_manager(self, __parse):
        __parse.return_value = 'fake query'
        self.app.get('/admin/deployments')
        args = self.deployments_manager.get_deployments.call_args[1]
        query = args['query']
        self.assertEqual(query, 'fake query')

    def test_parse_tenant_tag_before_sending_params_to_manager(self):
        self.tenant_manager.list_tenants.return_value = {'123': {}}
        self.app.get('/admin/deployments?tenant_tag=FOOBAR')
        args = self.deployments_manager.get_deployments.call_args[1]
        query = args['query']
        self.assertEqual(query['tenantId'], '123')

    def test_parse_tenant_tag_and_send_notenantsfound_query_to_manager(self):
        self.tenant_manager.list_tenants.return_value = {}
        self.app.get('/admin/deployments?tenant_tag=FOOBAR')
        args = self.deployments_manager.get_deployments.call_args[1]
        query = args['query']
        self.assertEqual(query['tenantId'], 'no-tenants-found')

    def test_remove_tenant_tag_before_sending_params_to_manager(self):
        self.tenant_manager.list_tenants.return_value = {'123': {}}
        self.app.get('/admin/deployments?tenant_tag=FOOBAR')
        args = self.deployments_manager.get_deployments.call_args[1]
        query = args['query']
        self.assertTrue('tenant_tag' not in query)

    def test_parse_blueprint_branch_before_sending_params_to_manager(self):
        self.tenant_manager.list_tenants.return_value = {'123': {}}
        self.app.get('/admin/deployments?blueprint_branch=FOOBAR')
        args = self.deployments_manager.get_deployments.call_args[1]
        query = args['query']
        alias = 'environment.providers.chef-solo.constraints.source'
        self.assertTrue(alias in query)
        self.assertEqual(query[alias], '%#FOOBAR')


class TestGetDeploymentCount(TestAdminRouter):

    @mock.patch.object(admin.router.utils.QueryParams, 'parse')
    def test_pass_query_params_to_manager(self, parse):
        self.deployments_manager.count.return_value = 99
        parse.return_value = 'fake query'
        self.app.get('/admin/deployments/count')
        self.deployments_manager.count.assert_called_with(
            tenant_id=mock.ANY,
            status=mock.ANY,
            query='fake query',
        )


class TestNotLoaded(TestAdminRouter):

    blueprints_manager = None

    def test_returns404(self):
        with self.assertRaises(exceptions.CheckmateException) as exc:
            self.app.get('/admin/cache/blueprints', expect_errors=True)
            self.assertEqual(exc.friendly_message, "Module not loaded")


class TestBlueprints(TestAdminRouter):
    """Test blueprint admin calls."""

    def test_returns_cache(self):
        """Admin call returns cached blueprints frm manager."""
        self.blueprints_manager.list_cache.return_value = {'results': {}}
        response = self.app.get('/admin/cache/blueprints')
        self.assertEqual(response.json, {'results': {}})


if __name__ == '__main__':
    test.run_with_params()
