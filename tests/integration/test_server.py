# pylint: disable=C0103,E1101

# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Tests for server module."""
import json
import logging
import mock
import sys
import unittest
import uuid

import bottle
import webtest

from checkmate import db
from checkmate import deployments
from checkmate import environments
from checkmate import middleware as cmmid
from checkmate import server
from checkmate import workflows

LOG = logging.getLogger(__name__)

try:
    import mongobox as mbox
    SKIP = False
    REASON = None
except ImportError as exc:
    LOG.warn("Unable to import MongoBox. MongoDB tests will not run: %s", exc)
    SKIP = True
    REASON = "'mongobox' not installed: %s" % exc
    mbox.MongoBox = object


@unittest.skipIf(SKIP, REASON)
class TestServer(unittest.TestCase):
    """Test Basic Server code."""
    COLLECTIONS_TO_CLEAN = ['tenants',
                            'deployments',
                            'blueprints',
                            'resource_secrets',
                            'resources']
    _connection_string = None

    @property
    def connection_string(self):
        """Property to return the db connection string."""
        return TestServer._connection_string

    #pylint: disable=W0603
    @classmethod
    def setUpClass(cls):
        """Fire up a sandboxed mongodb instance."""
        super(TestServer, cls).setUpClass()
        try:
            cls.box = mbox.MongoBox(scripting=True)
            cls.box.start()
            cls._connection_string = ("mongodb://localhost:%s/test" %
                                      cls.box.port)
        except StandardError as exc:
            LOG.exception(exc)
            if hasattr(cls, 'box'):
                del cls.box
            global SKIP
            global REASON
            SKIP = True
            REASON = str(exc)

    @classmethod
    def tearDownClass(cls):
        """Stop the sanboxed mongodb instance."""
        if hasattr(cls, 'box') and isinstance(cls.box, mbox.MongoBox):
            if cls.box.running() is True:
                cls.box.stop()
                cls.box = None
        super(TestServer, cls).tearDownClass()

    def setUp(self):
        if SKIP is True:
            self.skipTest(REASON)
        if self.connection_string:
            self.driver = db.get_driver(
                connection_string=self.connection_string, reset=True)
        bottle.default_app.push()
        reload(environments)
        self.root_app = bottle.default_app.pop()
        self.root_app.catchall = False

        deployments_manager = deployments.Manager()
        self.dep_router = deployments.Router(self.root_app,
                                             deployments_manager)

        workflows_manager = workflows.Manager()
        self.workflow_router = workflows.Router(self.root_app,
                                                workflows_manager,
                                                deployments_manager)

        tenant = cmmid.TenantMiddleware(self.root_app)
        context = cmmid.ContextMiddleware(tenant)
        extension = cmmid.ExtensionsMiddleware(context)
        self.app = webtest.TestApp(extension)

    def tearDown(self):
        for collection_name in TestServer.COLLECTIONS_TO_CLEAN:
            self.driver.database()[collection_name].drop()

    def test_multitenant_deployment(self):
        self.rest_tenant_exercise('deployment')

    def test_multitenant_environment(self):
        self.rest_tenant_exercise('environment')

    @mock.patch('checkmate.db.db_lock.DbLock')
    def test_multitenant_workflow(self, mock_db_lock):
        mock_db_lock()
        self.rest_tenant_exercise('workflow')

    def test_crosstenant_deployment(self):
        self.rest_cross_tenant_exercise('deployment')

    def test_crosstenant_environment(self):
        self.rest_cross_tenant_exercise('environment')

    @mock.patch('checkmate.db.db_lock.DbLock')
    def test_crosstenant_workflow(self, mock_db_lock):
        mock_db_lock()
        self.rest_cross_tenant_exercise('workflow')

    #
    # Functions called multiple times from above
    #
    def rest_exercise(self, model_name):
        """Exercise REST calls for both json and yaml."""
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
        """Check CRUD on tenants."""
        id1 = uuid.uuid4().hex[0:7]
        id2 = uuid.uuid4().hex[0:4]

        #PUT
        entity = "%s: &e1\n    id: '%s'" % (model_name, id1)
        res = self.app.put('/T1000/%ss/%s' % (model_name, id1), entity,
                           content_type='application/x-yaml')
        # TODO(any): make tests clean so we can predict if we get a 200 or 201
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
        self.assertIn(id1, data['results'])
        self.assertNotIn(id2, data)

        #GET (Tenant 2)
        res = self.app.get('/T2000/%ss' % model_name)
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        data = json.loads(res.body)
        self.assertIn(id2, data['results'])
        self.assertNotIn(id1, data['results'])

    def rest_cross_tenant_exercise(self, model_name):
        """Make sure tenant ID is respected."""
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

        # TODO(any): test posting object with bad tenant_id in it

    #
    # Other tests
    #
    def test_add_workflow(self):
        obj_id = uuid.uuid4().hex
        entity = {"id": obj_id, 'tenantId': 'T1000'}
        res = self.app.post_json('/T1000/workflows', entity)
        # TODO(any): make tests clean so we can predict if we get a 200 or 201
        self.assertIn(res.status, ['201 Created', '200 OK'])

    @mock.patch('checkmate.db.db_lock.DbLock')
    def test_save_workflow(self, mock_db_lock):
        mock_db_lock()
        obj_id = uuid.uuid4().hex
        entity = {"id": obj_id, 'tenantId': 'T1000'}
        res = self.app.post_json('/T1000/workflows/' + obj_id, entity)
        # TODO(any): make tests clean so we can predict if we get a 200 or 201
        self.assertIn(res.status, ['201 Created', '200 OK'])

    def test_unwrapped_deployment(self):
        """Using PUT /deployments/<oid> to exercise _content_to_deployment."""
        id1 = uuid.uuid4().hex[0:7]
        data = """
            id: '%s'
            """ % id1
        res = self.app.put('/T1000/deployments/%s' % id1, data,
                           content_type='application/x-yaml')
        self.assertIn(res.status, ['201 Created', '200 OK'])

    def test_wrapped_deployment(self):
        """Using PUT /deployments/<oid> to exercise _content_to_deployment."""
        id1 = uuid.uuid4().hex[0:7]
        data = """
            deployment:
                id: '%s'
            """ % id1
        res = self.app.put('/T1000/deployments/%s' % id1, data,
                           content_type='application/x-yaml')
        self.assertIn(res.status, ['201 Created', '200 OK'])

    def test_put_deployment_with_no_id_in_body(self):
        """Using PUT /deployments/<oid> to exercise _content_to_deployment."""
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
        """Using PUT /deployments/<oid> to exercise _content_to_deployment."""
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
        """Using PUT /deployments/<oid> to exercise _content_to_deployment."""
        self.root_app.error_handler = {500: server.error_formatter}
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
        """Check that GET /secrets responds."""
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
        """Check that POST /secrets responds."""
        id1 = uuid.uuid4().hex[0:7]
        data = """
            deployment:
                id: '%s'
            """ % id1
        self.app.put('/T1000/deployments/%s' % id1, data,
                     content_type='application/x-yaml')
        # Not an admin - 401
        res = self.app.post(
            '/T1000/deployments/%s/secrets' % id1,
            "A: 1",
            content_type='application/x-yaml',
            expect_errors=True
        )
        self.assertEqual(res.status, '401 Unauthorized')

        # Wrong tenant - 404 (don't divulge existence)
        res = self.app.post(
            '/T2000/deployments/%s/secrets' % id1,
            "A: 1",
            content_type='application/x-yaml',
            expect_errors=True
        )
        self.assertEqual(res.status, '404 Not Found')


if __name__ == '__main__':
    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
