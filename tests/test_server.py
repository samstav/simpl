#!/usr/bin/env python
import json
import os
import sys
import uuid

from bottle import default_app, load
import unittest2 as unittest
from webtest import TestApp

from checkmate.middleware import TenantMiddleware, ContextMiddleware
# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()

os.environ['CHECKMATE_DATA_PATH'] = os.path.join(os.path.dirname(__file__),
                                              'data')


class TestServer(unittest.TestCase):
    """ Test Basic Server code """

    def setUp(self):
        load('checkmate.blueprints')
        load('checkmate.components')
        load('checkmate.deployments')
        load('checkmate.environments')
        load('checkmate.workflows')
        root_app = default_app()
        root_app.catchall = False
        tenant = TenantMiddleware(root_app)
        context = ContextMiddleware(tenant)
        self.app = TestApp(context)

    def test_multitenant_deployment(self):
        self.rest_tenant_exercise('deployment')

    def test_multitenant_environment(self):
        self.rest_tenant_exercise('environment')

    def test_multitenant_component(self):
        self.rest_tenant_exercise('component')

    def test_multitenant_blueprint(self):
        self.rest_tenant_exercise('blueprint', 'b_id')

    def test_crosstenant_deployment(self):
        pass  # self.rest_cross_tenant_exercise('deployment')

    def test_crosstenant_environment(self):
        pass  # self.rest_cross_tenant_exercise('environment')

    def test_crosstenant_component(self):
        pass  # self.rest_cross_tenant_exercise('component')

    def test_crosstenant_blueprint(self):
        pass  # self.rest_cross_tenant_exercise('blueprint')

    def rest_exercise(self, model_name):
        #PUT
        entity = "%s: &e1\n    id: '1'" % model_name
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

    def rest_tenant_exercise(self, model_name, id='id'):
        #PUT
        entity = "%s: &e1\n    %s: '1'" % (model_name, id)
        res = self.app.put('/T1000/%ss/1' % model_name, entity,
                            content_type='application/x-yaml')
        self.assertEqual(res.status, '200 OK', res)
        self.assertEqual(res.content_type, 'application/json')

        entity = "%s: &e1\n    id: '2'" % model_name
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

    def rest_cross_tenant_exercise(self, model_name):
        """Make sure tenant ID is respected"""
        #PUT
        entity = "%s: &e1\n    id: 1" % model_name
        res = self.app.put('/T1000/%ss/1' % model_name, entity,
                            content_type='application/x-yaml')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')

        entity = "%s: &e1\n    id: 2" % model_name
        res = self.app.put('/T2000/%ss/2' % model_name, entity,
                            content_type='application/x-yaml')

        #GET (1 from T1000) - OK
        res = self.app.get('/T1000/%ss/1' % model_name)
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')

        #GET (1 from T2000) - SHOULD FAIL
        res = self.app.get('/T2000/%ss/1' % model_name)
        self.assertEqual(res.status, '404 Not Found')
        self.assertEqual(res.content_type, 'application/json')

        #TODO: test posting object with bad tenant_id in it

    def rest_add_workflow_test(self):
        obj_id = str(uuid.uuid4())
        entity = {"id": obj_id, 'tenantId': 'T1000'}
        res = self.app.post_json('/T1000/workflows', entity)
        self.assertEqual(res.status, '200 OK')

    def rest_save_workflow_test(self):
        obj_id = str(uuid.uuid4())
        entity = {"id": obj_id, 'tenantId': 'T1000'}
        res = self.app.post_json('/T1000/workflows/' + obj_id, entity)
        self.assertEqual(res.status, '200 OK')

    # def rest_post_workflow_task_test(self):
    #     workflow_id = str(uuid.uuid4())
    #     obj_id = str(uuid.uuid4())
    #     entity = {"id": obj_id}#, 'tenantId': 'T1000'}
    #     #TODO: check that uri task id and persisted id ==
    #     res = self.app.post_json('/T1000/workflows/'+workflow_id, entity)
    #     res = self.app.post_json('/T1000/workflows/%s/tasks/%s' % (workflow_id, obj_id), entity)
    #     self.assertEqual(res.status, '200 OK')

    #     get_obj = self.app.get("/T1000/workflows/1/tasks/"+ obj_id)

if __name__ == '__main__':
    # Run tests. Handle our paramsters separately
    import sys
    args = sys.argv[:]
    # Our --debug means --verbose for unitest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
