# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import json
import os
import sys
import unittest2 as unittest
import uuid

from bottle import default_app, load
from webtest import TestApp

os.environ['CHECKMATE_DATA_PATH'] = os.path.join(os.path.dirname(__file__),
                                                 'data')
os.environ['CHECKMATE_CONNECTION_STRING'] = 'sqlite://'

from checkmate import blueprints, deployments, environments, workflows
from checkmate.db import get_driver
from checkmate.middleware import (
    TenantMiddleware,
    ContextMiddleware,
    ExtensionsMiddleware,
)


class TestServer(unittest.TestCase):
    """ Test Basic Server code """

    def setUp(self):
        get_driver(connection_string=os.environ['CHECKMATE_CONNECTION_STRING'],
                   reset=True)
        reload(blueprints)
        reload(deployments)
        reload(environments)
        reload(workflows)
        root_app = default_app()
        root_app.catchall = False
        tenant = TenantMiddleware(root_app)
        context = ContextMiddleware(tenant)
        extension = ExtensionsMiddleware(context)
        self.app = TestApp(extension)

    def test_multitenant_deployment(self):
        self.rest_tenant_exercise('deployment')

    def test_multitenant_environment(self):
        self.rest_tenant_exercise('environment')

    def test_multitenant_workflow(self):
        self.rest_tenant_exercise('workflow')

    def test_multitenant_blueprint(self):
        self.rest_tenant_exercise('blueprint')

    def test_crosstenant_deployment(self):
        self.rest_cross_tenant_exercise('deployment')

    def test_crosstenant_environment(self):
        self.rest_cross_tenant_exercise('environment')

    def test_crosstenant_workflow(self):
        self.rest_cross_tenant_exercise('workflow')

    def test_crosstenant_blueprint(self):
        self.rest_cross_tenant_exercise('blueprint')

    def rest_exercise(self, model_name):
        id1 = uuid.uuid4().hex[0:7]
        id2 = uuid.uuid4().hex[0:4]

        #PUT
        entity = "%s: &e1\n    id: '%s'" % (model_name, id1)
        res = self.app.put('/%ss/1' % model_name, entity,
                           content_type='application/x-yaml')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')

        #GET (json)
        res = self.app.get('/%ss/%s' % (model_name, id1))
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')

        #GET (yaml)
        res = self.app.get('/%ss/%s' % (model_name, id1),
                           headers={'Accept': 'application/x-yaml'})
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/x-yaml')

        #LIST
        res = self.app.get('/%ss' % model_name)
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')

        #GET (both)
        res = self.app.get('/%ss' % model_name)
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        data = json.loads(res.body)
        self.assertIn(id1, data)
        self.assertIn(id2, data)

    def rest_tenant_exercise(self, model_name):
        '''Check CRUD on tenants'''
        id1 = uuid.uuid4().hex[0:7]
        id2 = uuid.uuid4().hex[0:4]

        #PUT
        entity = "%s: &e1\n    id: '%s'" % (model_name, id1)
        res = self.app.put('/T1000/%ss/%s' % (model_name, id1), entity,
                           content_type='application/x-yaml')
        #TODO: make tests clean so we can predict if we get a 200 or 201
        self.assertIn(res.status, ['201 Created', '200 OK'], res)
        self.assertEqual(res.content_type, 'application/json')

        entity = "%s: &e1\n    id: '%s'" % (model_name, id2)
        res = self.app.put('/T2000/%ss/%s' % (model_name, id2), entity,
                           content_type='application/x-yaml')

        #GET (1)
        res = self.app.get('/T1000/%ss/%s' % (model_name, id1))
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')

        #GET (2)
        res = self.app.get('/T2000/%ss/%s' % (model_name, id2))
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')

        #GET (Tenant 1)
        res = self.app.get('/T1000/%ss' % model_name)
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        data = json.loads(res.body)
        self.assertIn(id1, data)
        self.assertNotIn(id2, data)

        #GET (Tenant 2)
        res = self.app.get('/T2000/%ss' % model_name)
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        data = json.loads(res.body)
        self.assertIn(id2, data)
        self.assertNotIn(id1, data)

    def rest_cross_tenant_exercise(self, model_name):
        """Make sure tenant ID is respected"""
        id1 = uuid.uuid4().hex[0:7]
        id2 = uuid.uuid4().hex[0:4]

        #PUT
        entity = "%s: &e1\n    id: %s" % (model_name, id1)
        res = self.app.put('/T1000/%ss/%s' % (model_name, id1), entity,
                           content_type='application/x-yaml')
        self.assertEqual(res.status, '201 Created')
        self.assertEqual(res.content_type, 'application/json')

        entity = "%s: &e1\n    id: %s" % (model_name, id2)
        res = self.app.put('/T2000/%ss/%s' % (model_name, id2), entity,
                           content_type='application/x-yaml')

        #GET (1 from T1000) - OK
        res = self.app.get('/T1000/%ss/%s' % (model_name, id1))
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')

        #GET (1 from T2000) - SHOULD FAIL
        res = self.app.get('/T2000/%ss/%s' % (model_name, id1),
                           expect_errors=True)
        self.assertEqual(res.status, '404 Not Found')

        #TODO: test posting object with bad tenant_id in it

    def rest_add_workflow_test(self):
        obj_id = str(uuid.uuid4())
        entity = {"id": obj_id, 'tenantId': 'T1000'}
        res = self.app.post_json('/T1000/workflows', entity)
        #TODO: make tests clean so we can predict if we get a 200 or 201
        self.assertIn(res.status, ['201 Created', '200 OK'])

    def rest_save_workflow_test(self):
        obj_id = str(uuid.uuid4())
        entity = {"id": obj_id, 'tenantId': 'T1000'}
        res = self.app.post_json('/T1000/workflows/' + obj_id, entity)
        #TODO: make tests clean so we can predict if we get a 200 or 201
        self.assertIn(res.status, ['201 Created', '200 OK'])


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
