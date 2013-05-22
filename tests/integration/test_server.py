# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import json
import os
import sys
import unittest2 as unittest
import uuid

from bottle import default_app
from webtest import TestApp

from checkmate.server import error_formatter
from checkmate import blueprints, deployments, environments, workflows
from checkmate.middleware import (
    TenantMiddleware,
    ContextMiddleware,
    ExtensionsMiddleware,
)


class TestServer(unittest.TestCase):
    """ Test Basic Server code """

    def setUp(self):
        os.environ['CHECKMATE_CONNECTION_STRING'] = 'sqlite://'
        default_app.push()
        reload(blueprints)
        reload(deployments)
        reload(environments)
        reload(workflows)
        self.root_app = default_app.pop()
        self.root_app.catchall = False
        tenant = TenantMiddleware(self.root_app)
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

    #
    # Functions called multiple times from above
    #
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
        entity = "%s: &e1\n    id: '%s'" % (model_name, id1)
        res = self.app.put('/T1000/%ss/%s' % (model_name, id1), entity,
                           content_type='application/x-yaml')
        self.assertEqual(res.status, '201 Created')
        self.assertEqual(res.content_type, 'application/json')

        entity = "%s: &e1\n    id: '%s'" % (model_name, id2)
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

    #
    # Other tests
    #
    def test_add_workflow(self):
        obj_id = str(uuid.uuid4())
        entity = {"id": obj_id, 'tenantId': 'T1000'}
        res = self.app.post_json('/T1000/workflows', entity)
        #TODO: make tests clean so we can predict if we get a 200 or 201
        self.assertIn(res.status, ['201 Created', '200 OK'])

    def test_save_workflow(self):
        obj_id = str(uuid.uuid4())
        entity = {"id": obj_id, 'tenantId': 'T1000'}
        res = self.app.post_json('/T1000/workflows/' + obj_id, entity)
        #TODO: make tests clean so we can predict if we get a 200 or 201
        self.assertIn(res.status, ['201 Created', '200 OK'])

    def test_unwrapped_deployment(self):
        '''Using PUT /deployments/<oid> to exercise _content_to_deployment'''
        id1 = uuid.uuid4().hex[0:7]
        data = """
            id: '%s'
            """ % id1
        res = self.app.put('/T1000/deployments/%s' % id1, data,
                           content_type='application/x-yaml')
        self.assertIn(res.status, ['201 Created', '200 OK'])

    def test_wrapped_deployment(self):
        '''Using PUT /deployments/<oid> to exercise _content_to_deployment'''
        id1 = uuid.uuid4().hex[0:7]
        data = """
            deployment:
                id: '%s'
            """ % id1
        res = self.app.put('/T1000/deployments/%s' % id1, data,
                           content_type='application/x-yaml')
        self.assertIn(res.status, ['201 Created', '200 OK'])

    def test_put_deployment_with_no_id_in_body(self):
        '''Using PUT /deployments/<oid> to exercise _content_to_deployment'''
        id1 = uuid.uuid4().hex[0:7]
        data = """
            deployment:
                name: minimal deployment
            """
        res = self.app.put('/T1000/deployments/%s' % id1, data,
                           content_type='application/x-yaml')
        self.assertIn(res.status, ['201 Created', '200 OK'])
        self.assertIn('"id": "%s"' % id1, res.body)

    def test_put_deployment_with_includes(self):
        '''Using PUT /deployments/<oid> to exercise _content_to_deployment'''
        id1 = uuid.uuid4().hex[0:7]
        data = """
            deployment:
                id: '%s'
                includes: included stuff
            """ % id1
        res = self.app.put('/T1000/deployments/%s' % id1, data,
                           content_type='application/x-yaml')
        self.assertIn(res.status, ['201 Created', '200 OK'])
        self.assertNotIn('"includes":', res.body)

    def test_put_deployment_tenant_id_mismatch(self):
        '''Using PUT /deployments/<oid> to exercise _content_to_deployment'''
        self.root_app.error_handler = { 500: error_formatter }
        self.root_app.catchall = True
        id1 = uuid.uuid4().hex[0:7]
        data = """
            deployment:
                id: '%s'
                tenantId: allTheIDs
            """ % id1
        res = self.app.put(
            '/T1000/deployments/%s' % id1,
            data,
            content_type='application/x-yaml',
            headers={'Accept': 'application/x-yaml'},
            expect_errors=True
        )
        self.assertEqual(res.status, '400 Bad Request')
        self.assertIn('tenantId must match with current tenant ID', res.body)

    def test_get_deployment_secrets(self):
        '''Check that GET /secrets responds'''
        id1 = uuid.uuid4().hex[0:7]
        data = """
            deployment:
                id: '%s'
            """ % id1
        self.app.put('/T1000/deployments/%s' % id1, data,
                     content_type='application/x-yaml')
        # Not an admin - 401
        res = self.app.get('/T1000/deployments/%s/secrets' % id1,
                           expect_errors=True)
        self.assertEqual(res.status, '401 Unauthorized')

        # Wrong tenant - 404 (don't divulge existence)
        res = self.app.get('/T2000/deployments/%s/secrets' % id1,
                           expect_errors=True)
        self.assertEqual(res.status, '404 Not Found')

    def test_lock_deployment_secrets(self):
        '''Check that POST /secrets responds'''
        id1 = uuid.uuid4().hex[0:7]
        data = """
            deployment:
                id: '%s'
            """ % id1
        self.app.put('/T1000/deployments/%s' % id1, data,
                     content_type='application/x-yaml')
        # Not an admin - 401
        res = self.app.post('/T1000/deployments/%s/secrets' % id1, "A: 1",
                           content_type='application/x-yaml',
                           expect_errors=True)
        self.assertEqual(res.status, '401 Unauthorized')

        # Wrong tenant - 404 (don't divulge existence)
        res = self.app.post('/T2000/deployments/%s/secrets' % id1, "A: 1",
                           content_type='application/x-yaml',
                           expect_errors=True)
        self.assertEqual(res.status, '404 Not Found')


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
