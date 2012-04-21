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
        path =  os.path.join(os.environ['CHECKMATE_DATA_PATH'], 'environments')
        self.assertTrue(os.path.exists(os.path.join(path, '%s.%s' %
                                                    (data['id'], 'yaml'))))
        self.assertTrue(os.path.exists(os.path.join(path, '%s.%s' %
                                                    (data['id'], 'json'))))


if __name__ == '__main__':
    unittest.main()
