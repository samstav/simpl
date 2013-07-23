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


class TestGetDeployments(TestAdminRouter):

    def test_pass_query_params_to_manager(self):
        with mock.patch.object(self.router, '_get_filter_params'):
            self.router._get_filter_params.return_value = 'fake query'
            self.router.get_deployments()
            self.manager.get_deployments.assert_called_with(
                tenant_id=mock.ANY,
                offset=mock.ANY,
                limit=mock.ANY,
                with_deleted=mock.ANY,
                status=mock.ANY,
                query='fake query',
            )


class TestGetFilterParams(TestAdminRouter):

    def test_pass_empty_filter(self):
        query_params = {}
        with mock.patch.dict(bottle.request.query.dict, query_params):
            self.router.get_deployments()
            self.manager.get_deployments.assert_called_with(
                tenant_id=mock.ANY,
                offset=mock.ANY,
                limit=mock.ANY,
                with_deleted=mock.ANY,
                status=mock.ANY,
                query={}
            )

    def test_pass_only_whitelisted_params(self):
        query_params = {
            'name': ['fake name'],
            'blueprint.name': ['fake blue'],
            'search': ['fake search'],
            'evil_param': ['Muahaha'],
        }
        with mock.patch.dict(bottle.request.query.dict, query_params):
            self.router.get_deployments()
            self.manager.get_deployments.assert_called_with(
                tenant_id=mock.ANY,
                offset=mock.ANY,
                limit=mock.ANY,
                with_deleted=mock.ANY,
                status=mock.ANY,
                query={
                    'name': 'fake name',
                    'blueprint.name': 'fake blue',
                    'search': 'fake search',
                }
            )


class TestGetDeploymentCount(TestAdminRouter):

    def test_pass_query_params_to_manager(self):
        self.manager.count.return_value = 99
        with mock.patch.object(self.router, '_get_filter_params'):
            self.router._get_filter_params.return_value = 'fake query'
            self.router.get_deployment_count()
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
