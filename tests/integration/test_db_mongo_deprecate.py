# pylint: disable=C0103,W0212

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

"""Tests for MongoDB Driver (deprecated tests: don't add tests here)."""
import copy
import logging
import mock
import mox
import time
import unittest
import uuid

try:
    import mongobox as mbox

    SKIP = False
    REASON = None
except ImportError as exc:
    SKIP = True
    REASON = "'mongobox' not installed: %s" % exc
    mbox.MongoBox = object

from checkmate import db
from checkmate import utils
from checkmate.workflows import manager

LOG = logging.getLogger(__name__)


class TestDatabase(unittest.TestCase):
    #pylint: disable=W0603
    @classmethod
    def setUpClass(cls):
        """Fire up a sandboxed mongodb instance."""
        try:
            cls.box = mbox.MongoBox()
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

    def setUp(self):
        if SKIP is True:
            self.skipTest(REASON)
        self.collection_name = 'checkmate_test_%s' % uuid.uuid4().hex
        self.driver = db.get_driver(name='checkmate.db.mongodb.Driver',
                                    reset=True,
                                    connection_string=self._connection_string)
        self.driver._connection = self.driver._database = None  # reset driver
        self.driver.db_name = 'test'

        get_driver_patcher = mock.patch.object(manager.db, 'get_driver')
        mock_get_driver = get_driver_patcher.start()
        mock_get_driver.return_value = self.driver
        self.addCleanup(get_driver_patcher.stop)

        self.manager = manager.Manager()
        self.tenantId = "T1000"
        self.default_deployment = {
            'id': 'test',
            'name': 'test',
            'inputs': {},
            'includes': {},
            'resources': {},
            'workflow': "abcdef",
            'status': "NEW",
            'created': "yesterday",
            'tenantId': self.tenantId,
            'blueprint': {
                'name': 'test bp',
            },
            'environment': {
                'name': 'environment',
                'providers': {},
            },
        }

    def _decode_dict(self, dictionary):
        """Helper method to convert unicode to utf-8."""
        decoded_dict = {}
        for key, value in dictionary.iteritems():
            if isinstance(key, unicode):
                key = key.encode('utf-8')
                try:
                    key = int(key)
                except StandardError:
                    key = key
            if isinstance(value, unicode):
                value = value.encode('utf-8')
                if isinstance(value, int):
                    value = int(value)
            elif isinstance(value, dict):
                value = self._decode_dict(value)
            decoded_dict[key] = value
        return decoded_dict

    @unittest.skipIf(SKIP, REASON)
    def test_get_objects_for_empty_collections(self):
        self.assertEqual(len(self.driver._get_objects('foobars')), 3)

    @unittest.skipIf(SKIP, REASON)
    def test_objects(self):
        entity = {
            'id': 1,
            'name': 'My Component',
            'credentials': ['My Secrets']
        }
        body, secrets = utils.extract_sensitive_data(entity)
        results = self.driver._save_object(self.collection_name, entity['id'],
                                           body, secrets, tenant_id='T1000')
        self.assertDictEqual(results, body)

        results = self.driver._get_object(self.collection_name, entity['id'],
                                          with_secrets=True)
        entity['tenantId'] = 'T1000'  # gets added
        self.assertDictEqual(results, entity)
        self.assertIn('credentials', results)

        body['name'] = 'My Updated Component'
        entity['name'] = 'My Updated Component'
        results = self.driver._save_object(self.collection_name, entity['id'],
                                           body, secrets)
        results = self.driver._get_object(
            self.collection_name,
            entity['id'],
            with_secrets=True
        )
        self.assertIn('credentials', results)
        self.assertDictEqual(results, entity)

        results = self.driver._get_object(self.collection_name, entity['id'],
                                          with_secrets=False)
        self.assertNotIn('credentials', results)
        body['tenantId'] = 'T1000'  # gets added
        self.assertDictEqual(results, body)
        self.assertNotIn('_id', results, "Backend field '_id' should not be "
                                         "exposed outside of driver")

        results = self.driver._get_objects(self.collection_name,
                                           with_secrets=False,
                                           with_count=False)
        results = self._decode_dict(results)

        #Since object was extraced in _get_objects format, need to make sure
        #format of body matches
        expected_result_body = {1: body}

        self.assertIn('id', results['results'][1])
        self.assertEqual(results['results'][1]['id'], 1)
        self.assertDictEqual(results['results'], expected_result_body)

    @unittest.skipIf(SKIP, REASON)
    def test_pagination(self):
        entity = {
            'id': 1,
            'name': 'My Component',
            'credentials': ['My Secrets']
        }
        body, secrets = utils.extract_sensitive_data(entity)
        self.driver._save_object(self.collection_name, entity['id'], body,
                                 secrets, tenant_id='T1000')
        entity['id'] = 2
        entity['name'] = 'My Second Component'
        body, secrets = utils.extract_sensitive_data(entity)
        self.driver._save_object(self.collection_name, entity['id'], body,
                                 secrets, tenant_id='T1000')
        entity['id'] = 3
        entity['name'] = 'My Third Component'
        body, secrets = utils.extract_sensitive_data(entity)
        self.driver._save_object(self.collection_name, entity['id'], body,
                                 secrets, tenant_id='T1000')

        results = self.driver._get_objects(self.collection_name,
                                           tenant_id='T1000',
                                           with_secrets=False, limit=2,
                                           with_count=False)
        expected = {
            '_links': {},
            'results': {
                1: {
                    'id': 1,
                    'name': 'My Component',
                    'tenantId': 'T1000'
                },
                2: {
                    'id': 2,
                    'name': 'My Second Component',
                    'tenantId': 'T1000'
                }
            }
        }
        self.assertEqual(len(results), 2)
        self.assertDictEqual(results, expected)

        results = self.driver._get_objects(self.collection_name,
                                           tenant_id='T1000',
                                           with_secrets=False, offset=1,
                                           limit=2,
                                           with_count=False)
        expected = {
            '_links': {},
            'results': {
                2: {
                    'id': 2,
                    'name': 'My Second Component',
                    'tenantId': 'T1000'
                },
                3: {
                    'id': 3,
                    'name': 'My Third Component',
                    'tenantId': 'T1000'
                }
            }
        }
        self.assertEqual(len(results), 2)
        self.assertDictEqual(results, expected)

    @unittest.skipIf(SKIP, REASON)
    def test_hex_id(self):
        hex_id = uuid.uuid4().hex
        self.driver._save_object(self.collection_name,
                                 hex_id, dict(id=hex_id),
                                 None,
                                 tenant_id='T1000')
        unicode_results = self.driver._get_objects(self.collection_name,
                                                   with_count=False)
        if unicode_results and 'collection-count' in unicode_results:
            del unicode_results['collection-count']
        results = self._decode_dict(unicode_results)
        self.assertDictEqual(results['results'],
                             {hex_id: {"id": hex_id, 'tenantId': 'T1000'}})
        self.assertNotIn(
            '_id',
            results['results'],
            "Backend field '_id' should not be exposed outside of driver"
        )

    @unittest.skipIf(SKIP, REASON)
    def test_no_id_in_body(self):
        hex_id = uuid.uuid4().hex
        with self.assertRaises(AssertionError):
            self.driver._save_object('test', hex_id, {}, tenant_id='T1000')

    @unittest.skipIf(SKIP, REASON)
    def test_multiple_objects(self):
        expected = {}
        expected['_links'] = {}
        expected['results'] = {}
        for i in range(1, 5):
            expected['results'][i] = dict(id=i, tenantId='T1000')
            self.driver._save_object(self.collection_name, i, dict(id=i), None,
                                     tenant_id='T1000')
        unicode_results = self.driver._get_objects(self.collection_name,
                                                   with_count=False)
        results = self._decode_dict(unicode_results)
        self.assertDictEqual(results, expected)
        for i in range(1, 5):
            self.assertIn(i, results['results'])
            self.assertNotIn('_id', results['results'][i])
            self.assertEqual(results['results'][i]['id'], i)

    @unittest.skipIf(SKIP, REASON)
    def test_get_objects_with_total_count(self):
        expected = {}
        for i in range(1, 5):
            expected[i] = dict(id=i, tenantId='T1000')
            self.driver._save_object(self.collection_name, i, dict(id=i), None,
                                     tenant_id='T1000')
        unicode_results = self.driver._get_objects(self.collection_name,
                                                   with_count=True)
        self.assertIn('collection-count', unicode_results)

    @unittest.skipIf(SKIP, REASON)
    def test_save_new_deployment(self):
        dep_id = uuid.uuid4().hex
        self.default_deployment["id"] = dep_id
        self.default_deployment["resources"] = {'0': {'provider-key': 'test'},
                                                '1': {'foo': 'bar'}}

        deployment = self.driver.save_deployment(dep_id,
                                                 self.default_deployment,
                                                 partial=False,
                                                 tenant_id=self.tenantId)
        resource_list = []
        for key, value in deployment['resources'].items():
            resource_list.append({key: value})
        self.assertDictEqual(utils.flatten(resource_list),
                             utils.flatten(self._get_resources(dep_id)))

    @unittest.skipIf(SKIP, REASON)
    def test_save_new_deployment_with_secrets(self):
        dep_id = uuid.uuid4().hex
        self.default_deployment["id"] = dep_id
        self.default_deployment["resources"] = {'0': {'provider-key': 'test'}}
        expected_secret = {'0': {'instance': {'password': 'foo'}}}
        self.driver.save_deployment(dep_id, self.default_deployment,
                                    partial=False,
                                    tenant_id=self.tenantId,
                                    secrets=
                                    {"resources": expected_secret})

        deployment_secret = self.driver.database()["deployments_secrets"] \
            .find_one({"id": dep_id})

        resources = self._get_resources(deployment_id=dep_id, include_ids=True)
        resource_secret = self.driver.database()["resources_secrets"].find_one(
            {"_id": resources[0]["id"]}, {'_id': 0})

        self.assertIsNone(deployment_secret)
        self.assertDictEqual(expected_secret, resource_secret)

    @unittest.skipIf(SKIP, REASON)
    def test_full_deployment_update(self):
        dep_id = uuid.uuid4().hex
        self.default_deployment["id"] = dep_id
        self.default_deployment["resources"] = {'0': {'provider-key': 'test'},
                                                '1': {'foo': 'bar'}}
        deployment = self.driver.save_deployment(dep_id,
                                                 self.default_deployment,
                                                 partial=False,
                                                 tenant_id=self.tenantId)

        resources_after_first_save = self._get_resources(dep_id, True)

        deployment['resources'].pop('1')
        deployment['status'] = "PLANNED"
        deployment = self.driver.save_deployment(dep_id,
                                                 deployment,
                                                 partial=False,
                                                 tenant_id=self.tenantId)
        self.assertEqual(len(deployment['resources']), 1)
        self.assertIsNotNone(deployment['resources'].get('0', None))
        self.assertEqual(deployment['status'], "PLANNED")
        for resource in resources_after_first_save:
            self.assertIsNone(self.driver.database().resources.find_one(
                {'id': resource['id']}))
        resource_list = []
        for key, value in deployment['resources'].items():
            resource_list.append({key: value})
        self.assertItemsEqual(resource_list, self._get_resources(dep_id))

    def test_full_deployment_update_with_secrets(self):
        dep_id = uuid.uuid4().hex
        self.default_deployment["id"] = dep_id
        self.default_deployment["resources"] = {'0': {'provider-key': 'test'}}
        old_secret = {'0': {'instance': {'password': 'old_password'}}}

        deployment = self.driver.save_deployment(dep_id,
                                                 self.default_deployment,
                                                 partial=False,
                                                 tenant_id=self.tenantId,
                                                 secrets=
                                                 {"resources": old_secret})

        resources = self._get_resources(deployment_id=dep_id, include_ids=True)
        old_resource_secret = self.driver.database()[
            "resources_secrets"].find_one({"_id": resources[0]["id"]})

        expected_secret = {'0': {'instance': {'password': 'foo'}}}

        self.driver.save_deployment(dep_id,
                                    deployment,
                                    partial=False,
                                    tenant_id=self.tenantId,
                                    secrets={'resources': expected_secret})

        deployment_secret = self.driver.database()["deployments_secrets"] \
            .find_one({"id": dep_id})

        resources = self._get_resources(deployment_id=dep_id, include_ids=True)
        resource_secret = self.driver.database()["resources_secrets"].find_one(
            {"_id": resources[0]["id"]}, {'_id': 0})

        self.assertIsNone(deployment_secret)
        self.assertDictEqual(expected_secret, resource_secret)
        self.assertIsNone(self.driver.database()["resources_secrets"].find_one(
            {"_id": old_resource_secret["_id"]}))

    @unittest.skipIf(SKIP, REASON)
    def test_partial_deployment_update(self):
        dep_id = uuid.uuid4().hex
        resource_0 = {'provider-key': 'test'}
        self.default_deployment["id"] = dep_id
        self.default_deployment["resources"] = {'0': resource_0,
                                                '1': {'foo': 'bar'}}
        self.driver.save_deployment(dep_id,
                                    self.default_deployment,
                                    partial=False,
                                    tenant_id=self.tenantId,
                                    secrets={"clean": "encrypted"})
        new_resource_1 = {'foo': 'new_bar'}
        new_resource_2 = {'foo2': 'new_bar2'}
        resource_update = {
            'resources': {
                '1': new_resource_1,
                '2': new_resource_2,
            },
        }
        deployment = self.driver.save_deployment(dep_id, resource_update,
                                                 partial=True,
                                                 tenant_id=self.tenantId,
                                                 secrets=
                                                 {"clean": "encrypted1"})
        self.assertEqual(len(deployment['resources']), 3)
        db_secrets = self.driver.database()["deployments_secrets"]. \
            find_one({"_id": dep_id},
                     {"_id": 0})
        self.assertDictEqual({"clean": "encrypted1"}, db_secrets)

        resource_ids = []
        for db_resource in self._get_resources(dep_id, True):
            resource_ids.append(db_resource['id'])
        db_deployment = self.driver.database().deployments.find_one(
            {'_id': dep_id})
        self.assertItemsEqual(db_deployment['resources'], resource_ids)
        self.assertDictEqual(utils.flatten(self._get_resources(dep_id)),
                             utils.flatten([{'2': new_resource_2},
                                            {'1': new_resource_1},
                                            {'0': resource_0}]))

    @unittest.skipIf(SKIP, REASON)
    def test_partial_deployment_update_with_secrets(self):
        dep_id = uuid.uuid4().hex
        resource_0 = {'provider-key': 'test'}
        self.default_deployment["id"] = dep_id
        self.default_deployment["resources"] = {'0': resource_0}
        old_secret = {'0': {'instance': {'password': 'old_password'}}}
        self.driver.save_deployment(dep_id,
                                    self.default_deployment,
                                    partial=False,
                                    tenant_id=self.tenantId,
                                    secrets={'resources': old_secret})

        new_resource_1 = {'foo': 'new_bar'}
        new_secret = {'0': {'instance': {'password': 'new_password'}}}
        self.driver.save_deployment(dep_id,
                                    {'resources': {'0': new_resource_1}},
                                    partial=True,
                                    tenant_id=self.tenantId,
                                    secrets={'resources': new_secret})

        resources = self._get_resources(deployment_id=dep_id, include_ids=True)
        resource_secret = self.driver.database()["resources_secrets"].find_one(
            {"_id": resources[0]["id"]}, {'_id': 0})

        self.assertDictEqual(new_secret, resource_secret)

    @unittest.skipIf(SKIP, REASON)
    def test_partial_deployment_update_for_same_dep_and_resource_doc(self):
        dep_id = uuid.uuid4().hex
        resource_0 = {'provider-key': 'test'}
        self.default_deployment["id"] = dep_id
        self.default_deployment["_id"] = dep_id
        self.default_deployment["resources"] = {'0': resource_0,
                                                '1': {'foo': 'bar'}}
        self.driver.database().deployments.insert(self.default_deployment)

        new_resource_1 = {'foo': 'new_bar'}
        deployment = self.driver.save_deployment(dep_id,
                                                 {'resources': {
                                                     '1': new_resource_1}},
                                                 partial=True,
                                                 tenant_id=self.tenantId)
        self.assertEqual(len(deployment['resources']), 2)
        resource_ids = []
        for db_resource in self._get_resources(dep_id, True):
            resource_ids.append(db_resource['id'])
        db_deployment = self.driver.database().deployments.find_one(
            {'_id': dep_id})
        self.assertItemsEqual(db_deployment['resources'], resource_ids)
        self.assertDictEqual(utils.flatten(self._get_resources(dep_id)),
                             utils.flatten([{'1': new_resource_1},
                                            {'0': resource_0}]))

    @unittest.skipIf(SKIP, REASON)
    def test_partial_deployment_update_with_secrets_for_old_format(self):
        dep_id = uuid.uuid4().hex
        self.default_deployment["id"] = dep_id
        self.default_deployment["_id"] = dep_id
        self.default_deployment["resources"] = {'0': {'provider-key': 'test'}}

        self.driver.database().deployments.insert(self.default_deployment)
        self.driver.database().deployments_secrets.insert(
            {'_id': dep_id, 'resources': {'0': {'foo': 'bar'}}})

        new_secret = {'0': {'foo': 'new_secret'}}
        self.driver.save_deployment(dep_id,
                                    {'resources': {'0': {'foo': 'new_bar'}}},
                                    partial=True,
                                    tenant_id=self.tenantId,
                                    secrets={'resources': new_secret})
        resources = self._get_resources(deployment_id=dep_id, include_ids=True)
        resource_secret = self.driver.database()["resources_secrets"].find_one(
            {"_id": resources[0]["id"]}, {'_id': 0})
        self.assertIsNone(self.driver.database().deployments_secrets.find_one(
            {'_id': dep_id}))
        self.assertDictEqual(resource_secret, new_secret)

    @unittest.skipIf(SKIP, REASON)
    def test_get_deployment(self):
        dep_id = uuid.uuid4().hex
        self.default_deployment["id"] = dep_id
        self.default_deployment["resources"] = {'0': {'provider-key': 'test'},
                                                '1': {'foo': 'bar'}}
        deployment = self.driver.save_deployment(dep_id,
                                                 self.default_deployment,
                                                 partial=False,
                                                 tenant_id=self.tenantId)

        load_deployment = self.driver.get_deployment(dep_id)

        self.assertDictEqual(deployment["resources"],
                             load_deployment["resources"])

    @unittest.skipIf(SKIP, REASON)
    def test_get_deployment_with_secrets(self):
        dep_id = uuid.uuid4().hex
        self.default_deployment["id"] = dep_id
        self.default_deployment["resources"] = {'0': {'provider-key': 'test'},
                                                '1': {'foo': 'bar'}}
        self.driver.save_deployment(dep_id,
                                    self.default_deployment,
                                    partial=False,
                                    tenant_id=self.tenantId,
                                    secrets={
                                        'resources': {
                                            '0': {'password': 'foo'}}})

        load_deployment = self.driver.get_deployment(dep_id, with_secrets=True)

        expected_resources = {'0': {'provider-key': 'test', 'password': 'foo'},
                              '1': {'foo': 'bar'}}
        self.assertDictEqual(expected_resources, load_deployment["resources"])

    def _get_resources(self, deployment_id, include_ids=False):
        """Helper method that returns the resources from a deployment."""
        db_deployment = self.driver.database().deployments.find_one(
            {'_id': deployment_id}, {'resources': 1, '_id': 0})
        db_resources = db_deployment['resources']
        resources = []
        resources_projection = {'_id': 0, 'tenantId': 0, 'id': 0}
        if include_ids:
            resources_projection.pop('id')
        for resource_id in db_resources:
            resource = self.driver.database().resources.find_one(
                {'_id': resource_id}, resources_projection)
            resources.append(resource)
        return resources

    @unittest.skipIf(SKIP, REASON)
    def test_create_and_delete_lock(self):
        key = uuid.uuid4()
        with self.driver.lock(key, 36000):
            lock_entry = self.driver.database()['locks'].find_one({"_id": key})
            self.assertIsNotNone(lock_entry)
            self.assertTrue("expires_at" in lock_entry)
        lock = self.driver.database()['locks'].find_one({"_id": key})
        self.assertIsNone(lock)

    @unittest.skipIf(SKIP, REASON)
    def test_lock_for_existing_lock(self):
        key = uuid.uuid4()
        self.driver.database()['locks'].insert(
            {"_id": key, "expires_at": time.time() + 20})
        try:
            with self.driver.lock(key, 200):
                pass
        except db.ObjectLockedError:
            raised = True
        self.assertTrue(raised)

    @unittest.skipIf(SKIP, REASON)
    def test_create_new_lock_for_expired_locks(self):
        key = uuid.uuid4()
        current_time = time.time()
        self.driver.database()['locks'].insert(
            {"_id": key, "expires_at": current_time - 20})
        with self.driver.lock(key, 10):
            lock_entry = self.driver.database()['locks'].find_one({"_id": key})
            self.assertIsNotNone(lock_entry)
            self.assertGreater(lock_entry["expires_at"], current_time)

    @unittest.skipIf(SKIP, REASON)
    def test_acquire_lock_for_two_sequential_calls_with_existing_lock(self):
        key = uuid.uuid4()
        current_time = time.time()
        self.driver.database()['locks'].insert(
            {"_id": key, "expires_at": current_time - 20})
        self.driver.acquire_lock(key, 20)
        self.assertRaises(db.ObjectLockedError, self.driver.acquire_lock, key,
                          20)
        self.driver.release_lock(key)

    @unittest.skipIf(SKIP, REASON)
    def test_acquire_lock_for_two_sequential_calls_without_existing_lock(self):
        key = uuid.uuid4()
        _mox = mox.Mox()
        _mox.StubOutWithMock(self.driver, '_find_existing_lock')
        self.driver._find_existing_lock(key).AndReturn(False)
        self.driver._find_existing_lock(key).AndReturn(False)

        _mox.ReplayAll()

        self.driver.acquire_lock(key, 20)
        self.assertRaises(db.ObjectLockedError, self.driver.acquire_lock, key,
                          20)
        self.driver.release_lock(key)

        _mox.VerifyAll()

    @unittest.skipIf(SKIP, REASON)
    def test_unlock(self):
        key = uuid.uuid4()
        self.driver.database()['locks'].insert(
            {"_id": key, "expires_at": time.time() + 20})
        self.assertRaises(db.ObjectLockedError, self.driver.lock, key, 100)

        self.driver.unlock(key)
        lock = self.driver.database()['locks'].find_one({"_id": key})
        self.assertIsNone(lock)
        self.assertIsInstance(self.driver.lock(key, 100), db.db_lock.DbLock)

        self.assertRaises(db.InvalidKeyError, self.driver.unlock, "X")

    @unittest.skipIf(SKIP, REASON)
    def test_raise_if_trying_to_unlock_non_existent_key(self):
        self.assertRaises(db.InvalidKeyError, self.driver.unlock, uuid.uuid4())


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
