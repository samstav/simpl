#!/usr/bin/env python
import bottle
import json
import os
import unittest2 as unittest
from webtest import TestApp

os.environ['CHECKMATE_DATA_PATH'] = os.path.join(os.path.dirname(__file__),
                                              'data')
os.environ['BROKER_USERNAME'] = os.environ.get('BROKER_USERNAME', 'checkmate')
os.environ['BROKER_PASSWORD'] = os.environ.get('BROKER_PASSWORD', 'password')
os.environ['BROKER_HOST'] = os.environ.get('BROKER_HOST', 'localhost')
os.environ['BROKER_PORT'] = os.environ.get('BROKER_PORT', '5672')


class TestServer(unittest.TestCase):
    """ Test Basic Server code """

    def setUp(self):
        self.app = TestApp(bottle.app())

    def test_REST_deployment(self):
        self.rest_exercise('deployment')

    def test_REST_environment(self):
        self.rest_exercise('environment')

    def test_REST_component(self):
        self.rest_exercise('component')

    def test_REST_blueprint(self):
        self.rest_exercise('blueprint')

    def test_multitenant_deployment(self):
        self.rest_tenant_exercise('deployment')

    def test_multitenant_environment(self):
        self.rest_tenant_exercise('environment')

    def test_multitenant_component(self):
        self.rest_tenant_exercise('component')

    def test_multitenant_blueprint(self):
        self.rest_tenant_exercise('blueprint')

    def rest_exercise(self, model_name):
        #PUT
        entity = "%s: &e1\n    id: 1" % model_name
        res = self.app.put('/%ss/1' % model_name, entity,
                            content_type='application/x-yaml')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')

        #GET (json)
        res = self.app.get('/%ss/1' % model_name)
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')

        #GET (yaml)
        res = self.app.get('/%ss/1' % model_name,
                           headers={'Accept': 'application/x-yaml'})
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/x-yaml')

        #LIST
        res = self.app.get('/%ss' % model_name)
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')

    def rest_tenant_exercise(self, model_name):
        #PUT
        entity = "%s: &e1\n    id: 1" % model_name
        res = self.app.put('/T1000/%ss/1' % model_name, entity,
                            content_type='application/x-yaml')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')

        entity = "%s: &e1\n    id: 2" % model_name
        res = self.app.put('/T2000/%ss/2' % model_name, entity,
                            content_type='application/x-yaml')

        #GET (1)
        res = self.app.get('/%ss/1' % model_name)
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')

        #GET (2)
        res = self.app.get('/%ss/2' % model_name)
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')

        #GET (both)
        res = self.app.get('/%ss' % model_name)
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        data = json.loads(res.body)
        self.assertIn('1', data)
        self.assertIn('2', data)

        #GET (Tenant 1)
        res = self.app.get('/T1000/%ss' % model_name)
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        data = json.loads(res.body)
        self.assertIn('1', data)
        self.assertNotIn('2', data)

        #GET (Tenant 2)
        res = self.app.get('/T2000/%ss' % model_name)
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        data = json.loads(res.body)
        self.assertIn('2', data)
        self.assertNotIn('1', data)

if __name__ == '__main__':
    unittest.main(verbosity=2)
