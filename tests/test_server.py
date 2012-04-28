#!/usr/bin/env python
import bottle
import json
import os
import unittest2 as unittest
from webtest import TestApp
import yaml

os.environ['CHECKMATE_DATA_PATH'] = os.path.join(os.path.dirname(__file__),
                                                 'data')
from checkmate import server


class test_server(unittest.TestCase):
    """ Test Basic Server code """

    def setUp(self):
        self.app = TestApp(bottle.app())

    def test_environments_get(self):
        res = self.app.get('/environments')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')

    def test_environments_post(self):
        environment = """environment: &env1
  name: rackcloudtech-test
  providers:
  - compute: &rax-cloud-servers
    endpoint: https://servers.api.rakcpsacecloud.com/servers/{tenantId}
  - loadbalancer: &rax-lbaas
    endpoint: https://lbaas.api.rakcpsacecloud.com/servers/{tenantId}
  - database: &rax-dbaas
    endpoint: https://database.api.rakcpsacecloud.com/servers/{tenantId}
  - common:
    vendor: rackspace
    credentials:
    - token: {token}"""
        res = self.app.post('/environments', environment,
                            content_type='application/x-yaml')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        data = json.loads(res.body)


    def test_REST_deployment(self):
        self.rest_exercise('deployment')

    def test_REST_environment(self):
        self.rest_exercise('environment')

    def test_REST_component(self):
        self.rest_exercise('component')

    def test_REST_blueprint(self):
        self.rest_exercise('blueprint')

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

if __name__ == '__main__':
    unittest.main(verbosity=2)
