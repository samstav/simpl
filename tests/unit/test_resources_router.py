import mock
import unittest

import bottle
import webtest

from checkmate import resources
from checkmate import test


class TestResourcesRouter(unittest.TestCase):
    def setUp(self):
        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.app = webtest.TestApp(self.filters)

        self.manager = mock.Mock()
        self.router = resources.Router(self.root_app, self.manager)

    @unittest.skip
    def test_pass_params_to_manager(self):
        self.router.get_resources(tenant_id=123, offset=1, limit=3,
                                  resource_type='load-balancer',
                                  provider='load-ballooncer')
        self.manager.get_resources.assert_called_with(
            tenant_id=123,
            offset=1,
            limit=3,
            resource_type='load-balancer',
            provider='load-ballooncer'
        )
