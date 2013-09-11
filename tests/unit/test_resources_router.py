import mock
import unittest

import bottle
import webtest

from checkmate import resources
from checkmate import test


class TestResourcesRouterGetResources(unittest.TestCase):
    def setUp(self):
        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.app = webtest.TestApp(self.filters)

        self.manager = mock.Mock()
        self.router = resources.Router(self.root_app, self.manager)
        self.manager.get_resources.return_value = {
            'results': [],
            'collection-count': 0
        }

    def test_passes_the_tenant_id(self):
        self.app.get('/123/resources')
        _, kwargs = self.manager.get_resources.call_args
        self.assertEqual(kwargs['tenant_id'], '123')

    def test_passes_the_limit(self):
        self.app.get('/123/resources?limit=6')
        _, kwargs = self.manager.get_resources.call_args
        self.assertEqual(kwargs['limit'], 6)

    def test_passes_the_offset(self):
        self.app.get('/123/resources?offset=7')
        _, kwargs = self.manager.get_resources.call_args
        self.assertEqual(kwargs['offset'], 7)

    def test_passes_the_resource_type(self):
        self.app.get('/123/resources?type=foobar')
        _, kwargs = self.manager.get_resources.call_args
        self.assertEqual(kwargs['query']['resource_type'], 'foobar')

    def test_passes_the_provider(self):
        self.app.get('/123/resources?provider=fakeprovider')
        _, kwargs = self.manager.get_resources.call_args
        self.assertEqual(kwargs['query']['provider'], 'fakeprovider')

    def test_passes_the_resource_ids(self):
        self.app.get('/123/resources?id=1&id=2&id=foobar')
        _, kwargs = self.manager.get_resources.call_args
        self.assertEqual(kwargs['query']['resource_ids'], ['1', '2', 'foobar'])
