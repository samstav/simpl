# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method
'''
import mock
import unittest
import webtest

import bottle

from checkmate import admin
from checkmate import test


class TestAdminRouter(unittest.TestCase):

    def setUp(self):
        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.filters.context.is_admin = True
        self.app = webtest.TestApp(self.filters)

        self.manager = mock.Mock()
        self.tenant_manager = mock.Mock()
        self.router = admin.Router(self.root_app, self.manager,
                                   self.tenant_manager)

        results = {'_links': {}, 'results': {}, 'collection-count': 0}
        self.manager.get_deployments.return_value = results


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
        res = self.app.get('/admin/deployments')
        args = self.manager.get_deployments.call_args[1]
        query = args['query']
        self.assertEqual(query, 'fake query')

    def test_parse_tenant_tag_before_sending_params_to_manager(self):
        self.tenant_manager.list_tenants.return_value = { '123': { } }
        res = self.app.get('/admin/deployments?tenant_tag=FOOBAR')
        args = self.manager.get_deployments.call_args[1]
        query = args['query']
        self.assertEqual(query['tenantId'], '123')

    def test_parse_tenant_tag_and_send_notenantsfound_query_to_manager(self):
        self.tenant_manager.list_tenants.return_value = {}
        res = self.app.get('/admin/deployments?tenant_tag=FOOBAR')
        args = self.manager.get_deployments.call_args[1]
        query = args['query']
        self.assertEqual(query['tenantId'], 'no-tenants-found')

    def test_remove_tenant_tag_before_sending_params_to_manager(self):
        self.tenant_manager.list_tenants.return_value = { '123': { } }
        res = self.app.get('/admin/deployments?tenant_tag=FOOBAR')
        args = self.manager.get_deployments.call_args[1]
        query = args['query']
        self.assertTrue('tenant_tag' not in query)

    def test_parse_blueprint_branch_before_sending_params_to_manager(self):
        self.tenant_manager.list_tenants.return_value = { '123': { } }
        res = self.app.get('/admin/deployments?blueprint_branch=FOOBAR')
        args = self.manager.get_deployments.call_args[1]
        query = args['query']
        alias = 'environment.providers.chef-solo.constraints.source'
        self.assertTrue(alias in query)
        self.assertEqual(query[alias], '%#FOOBAR')


class TestGetDeploymentCount(TestAdminRouter):

    @mock.patch.object(admin.router.utils.QueryParams, 'parse')
    def test_pass_query_params_to_manager(self, parse):
        self.manager.count.return_value = 99
        parse.return_value = 'fake query'
        res = self.app.get('/admin/deployments/count')
        self.manager.count.assert_called_with(
            tenant_id=mock.ANY,
            status=mock.ANY,
            query='fake query',
        )


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
