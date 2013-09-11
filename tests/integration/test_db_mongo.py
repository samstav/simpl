# pylint: disable=R0904

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

"""Tests for MongoDB Driver."""
import logging
import unittest

from tests.integration import base

LOG = logging.getLogger(__name__)
try:
    import mongobox as mbox
    from mongobox.unittest import MongoTestCase
    SKIP = False
    REASON = None
except ImportError as exc:
    LOG.warn("Unable to import MongoBox. MongoDB tests will not run: %s", exc)
    SKIP = True
    REASON = "'mongobox' not installed: %s" % exc
    mbox.MongoBox = object


@unittest.skipIf(SKIP, REASON)
class TestDBMongo(base.DBDriverTests, MongoTestCase):
    COLLECTIONS_TO_CLEAN = ['tenants',
                            'deployments',
                            'blueprints',
                            'resource_secrets',
                            'resources']
    _connection_string = None

    @property
    def connection_string(self):
        return TestDBMongo._connection_string

    #pylint: disable=W0603
    @classmethod
    def setUpClass(cls):
        """Fire up a sandboxed mongodb instance."""
        super(TestDBMongo, cls).setUpClass()
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
        super(TestDBMongo, cls).tearDownClass()

    def setUp(self):
        if SKIP is True:
            self.skipTest(REASON)
        base.DBDriverTests.setUp(self)

    def tearDown(self):
        for collection_name in TestDBMongo.COLLECTIONS_TO_CLEAN:
            self.driver.database()[collection_name].drop()

    def test_merge_secrets(self):
        self.driver.database()["resources_secrets"].insert({
            '_id': '12345',
            'id': '12345',
            'sync_keys': {'foo': 'bar'},
            '1': {'instance': {'password': '13Xfdge'}}
        })
        body = {'id': '12345', '1': {'instance': {'id': '1'}}}
        self.driver.merge_secrets("resources", '12345', body)
        expected = {
            'id': '12345',
            '1': {
                'instance': {
                    'id': '1',
                    'password': '13Xfdge',
                },
            }
        }
        self.assertDictEqual(body, expected)

    def test_get_deployments_does_not_return__id(self):
        self.driver.database()['deployments'].insert({
            '_id': 'abc',
            'id': '123',
            'tenantId': '321'
        })
        result = self.driver.get_deployments()
        expected = {'123': {'id': '123', 'tenantId': '321'}}
        self.assertDictEqual(result['results'], expected)

    def test_get_deployments_with_offset(self):
        self.driver.database()['deployments'].insert([
            {'id': '123', 'tenantId': '321'},
            {'id': '777', 'tenantId': '888'}
        ])
        result = self.driver.get_deployments(offset=1)
        expected = {'777': {'id': '777', 'tenantId': '888'}}
        self.assertDictEqual(result['results'], expected)

    def test_get_resources_does_not_return__id(self):
        self.driver.database()['resources'].insert({
            '_id': 'abc',
            'id': '123',
            'tenantId': '321'
        })
        result = self.driver.get_resources()
        expected = {'123': {'id': '123', 'tenantId': '321'}}
        self.assertDictEqual(result['results'], expected)

    def test_get_resources_with_tenant_id(self):
        self.driver.database()['resources'].insert([
            {'id': '123', 'tenantId': '321'},
            {'id': '777', 'tenantId': '888'}
        ])
        result = self.driver.get_resources(tenant_id='888')
        expected = {'777': {'id': '777', 'tenantId': '888'}}
        self.assertDictEqual(result['results'], expected)

    def test_get_resources_with_limit(self):
        self.driver.database()['resources'].insert([
            {'id': '123', 'tenantId': '321'},
            {'id': '777', 'tenantId': '888'}
        ])
        result = self.driver.get_resources(limit=1)
        expected = {'123': {'id': '123', 'tenantId': '321'}}
        self.assertDictEqual(result['results'], expected)

    def test_get_resources_with_offset(self):
        self.driver.database()['resources'].insert([
            {'id': '123', 'tenantId': '321'},
            {'id': '777', 'tenantId': '888'}
        ])
        result = self.driver.get_resources(offset=1)
        expected = {'777': {'id': '777', 'tenantId': '888'}}
        self.assertDictEqual(result['results'], expected)

    def test_get_resources_with_resource_ids(self):
        self.driver.database()['resources'].insert([
            {'id': '123', 'tenantId': '321',
                '4': {'instance': {'id': 'id1'}}},
            {'id': '777', 'tenantId': '888',
                '4': {'instance': {'id': 'id2'}}},
            {'id': '999', 'tenantId': '123',
                '4': {'instance': {'id': 'id3'}}}
        ])
        result = self.driver.get_resources(resource_ids=['id1', 'id3'])
        self.assertIsNone(result['results'].get('777'))
        self.assertEqual(len(result['results']), 2)


@unittest.skipIf(SKIP, REASON)
class TestMongoDBCapabilities(unittest.TestCase):
    """Test MongoDB's capabilities against our driver design

    We do things like document partial updates and locking with mongodb. The
    way we do that might break with certain versions of Mongo, so this test
    module validates that our designs work as expected.

    These tests are optional. If MongoDB is not installed, they will be
    skipped.
    """
    #pylint: disable=W0603
    @classmethod
    def setUpClass(cls):
        """Fire up a sandboxed mongodb instance."""
        try:
            cls.box = mbox.MongoBox()
            cls.box.start()
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

    def setUp(self):
        """Get a client conection to our sandboxed mongodb instance."""
        if hasattr(self, 'box'):
            self.client = self.box.client()
        else:
            raise unittest.SkipTest("No sandboxed mongoDB")

    def tearDown(self):
        """Disconnect the client."""
        if hasattr(self, 'box'):
            self.client = None

    def test_mongo_instance(self):
        """Verify the mongobox's mongodb instance is working."""
        self.assertTrue(self.client.alive())

    def test_mongo_object_creation(self):
        """Verify object creation."""
        col = self.client.tdb.c1
        col.save({})
        self.assertIn('tdb', self.client.database_names())
        self.assertIn('c1', self.client.tdb.collection_names())
        self.assertEqual(1, col.count())

    def test_mongo_custom_id(self):
        """Verify assigning IDs."""
        col = self.client.tdb.c2
        col.save({'id': 'our-id'})
        result = col.find_one({'id': 'our-id'})
        self.assertIn('id', result, msg="Our ID was not returned")
        self.assertIn('_id', result, msg="Mongo no longer has an _id field")
        self.assertEqual(len(result), 2, msg="Mongo added unexpected fields")
        self.assertNotEqual(result['id'], result['_id'],
                            msg="Mongo's and our IDs are now the same")
        self.assertEqual(result['id'], 'our-id', msg="Our ID is not intact")

    def test_mongo_projection(self):
        """We can return our IDs with only specific fields."""
        col = self.client.tdb.c3
        col.save({'id': 'our-id', 'name': 'Ziad', 'hide': 'X'})
        result = col.find_one(
            {'id': 'our-id'},
            {
                '_id': 0,
                'hide': 0
            }
        )
        self.assertDictEqual(result, {'id': 'our-id', 'name': 'Ziad'})

    def test_partial_update(self):
        """We can update only specific fields."""
        col = self.client.tdb.c4
        col.save({'id': 'our-id', 'status': 'PLANNED', 'name': 'Ziad'})
        obj = col.find_one({'id': 'our-id'}, {'_id': 0})
        self.assertIn('name', obj, msg="'name' was not saved")

        col.update(
            {'id': 'our-id'},
            {
                '$set': {
                    'status': 'UP'
                }
            }
        )
        obj = col.find_one({'id': 'our-id'}, {'_id': 0})
        self.assertIn('name', obj, msg="'name' was removed by an update")
        self.assertDictEqual(obj, {'id': 'our-id', 'status': 'UP',
                                   'name': 'Ziad'})

    def test_deep_partial_unsupported(self):
        """Mongo update is like a dict.update() - it overwrites whole keys."""
        col = self.client.tdb.c5
        col.save(
            {
                'id': 'our-id',
                'status': 'PLANNED',
                'subobj': {
                    'name': 'Ziad',
                    'status': 'busy',
                }
            }
        )

        col.update(
            {'id': 'our-id'},
            {
                '$set': {
                    'status': 'UP',
                    'subobj': {
                        'status': 'gone fishing'
                    }
                }
            }
        )
        obj = col.find_one({'id': 'our-id'}, {'_id': 0})
        self.assertIn('id', obj, msg="'id' was removed by an update")
        self.assertIn('subobj', obj, msg="'subobj' was removed by an update")
        subobj = obj['subobj']
        self.assertNotIn('name', subobj, msg="Writing partials now works!!!")
        self.assertDictEqual(obj, {
            'id': 'our-id',
            'status': 'UP',
            'subobj': {
                'status': 'gone fishing'
            }
        })

    def test_write_if_zero(self):
        """Verify that syntax for locking an object works."""
        col = self.client.tdb.c6
        col.save(
            {
                'id': 'our-id',
                '_lock': 0
            }
        )
        obj = col.find_and_modify(
            query={
                '$or': [{'_lock': {'$exists': False}}, {'_lock': 0}]
            },
            update={
                '$set': {
                    '_lock': "1",
                }
            },
            fields={'_lock': 0, '_id': 0}
        )
        self.assertEqual(obj['id'], 'our-id')

    def test_write_if_field_not_exists(self):
        """Verify that syntax for locking an object works."""
        col = self.client.tdb.c7
        col.save(
            {
                'id': 'our-id',
            }
        )
        obj = col.find_and_modify(
            query={
                '$or': [{'_lock': {'$exists': False}}, {'_lock': 0}]
            },
            update={
                '$set': {
                    '_lock': "1",
                }
            },
            fields={'_lock': 0, '_id': 0}
        )
        self.assertEqual(obj['id'], 'our-id')

    def test_skip_if_filtered(self):
        """Verify that syntax for locking an object works."""
        col = self.client.tdb.c8
        col.save(
            {
                'id': 'our-id',
                '_lock': 'my-key'
            }
        )
        obj = col.find_and_modify(
            query={
                '$or': [{'_lock': {'$exists': False}}, {'_lock': 0}]
            },
            update={
                '$set': {
                    '_lock': "1",
                }
            },
            fields={'_lock': 0, '_id': 0}
        )
        self.assertIsNone(obj)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
