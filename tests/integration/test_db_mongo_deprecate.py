# pylint: disable=C0103,W0212
"""Tests for MongoDB Driver (deprecated tests: don't add tests here)."""
import copy
import logging
import mox
import time
import unittest
import uuid

try:
    from mongobox import MongoBox

    SKIP = False
    REASON = None
except ImportError as exc:
    SKIP = True
    REASON = "'mongobox' not installed: %s" % exc
    MongoBox = object


from checkmate import db
from checkmate import utils
from checkmate.db import db_lock
from checkmate.utils import extract_sensitive_data
from checkmate.workflows import manager

LOG = logging.getLogger(__name__)


class TestDatabase(unittest.TestCase):
    #pylint: disable=W0603
    @classmethod
    def setUpClass(cls):
        """Fire up a sandboxed mongodb instance"""
        try:
            cls.box = MongoBox()
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
        """Stop the sanboxed mongodb instance"""
        if hasattr(cls, 'box') and isinstance(cls.box, MongoBox):
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
        self.manager = manager.Manager({'default': self.driver})
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
        body, secrets = extract_sensitive_data(entity)
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
        body, secrets = extract_sensitive_data(entity)
        self.driver._save_object(self.collection_name, entity['id'], body,
                                 secrets, tenant_id='T1000')
        entity['id'] = 2
        entity['name'] = 'My Second Component'
        body, secrets = extract_sensitive_data(entity)
        self.driver._save_object(self.collection_name, entity['id'], body,
                                 secrets, tenant_id='T1000')
        entity['id'] = 3
        entity['name'] = 'My Third Component'
        body, secrets = extract_sensitive_data(entity)
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
    def test_lock_existing_object(self):
        klass = 'workflows'
        obj_id = 1
        self.driver.database()[klass].remove({'_id': obj_id})
        self.driver._save_object(klass, obj_id, {"id": obj_id, "test": obj_id},
                                 tenant_id='T1000')

        locked_object, key = self.driver.lock_object(klass, obj_id)
        #is the returned object what we expected?
        self.assertEqual(locked_object, {"id": obj_id, "tenantId": "T1000",
                                         "test": obj_id})
        #was a key generated?
        self.assertTrue(key)
        stored_object = self.driver.database()[klass].find_one({"_id": obj_id})
        #was the key stored correctly?
        self.assertEqual(key, stored_object['_lock'])
        #was a _lock_timestamp generated
        self.assertTrue('_lock_timestamp' in stored_object)

    @unittest.skipIf(SKIP, REASON)
    def test_unlock_existing_object(self):
        klass = 'workflows'
        obj_id = 1
        original = {
            "tenantId": "T1000",
            "test": obj_id,
        }
        setup_obj = copy.copy(original)
        setup_obj.update({
            "_lock": 0,
            "_id": obj_id,
        })
        self.driver.database()[klass].remove({'_id': obj_id})

        #setup unlocked workflow
        self.driver.database()[klass].find_and_modify(
            query={"_id": obj_id},
            update=setup_obj,
            fields={
                '_id': 0,
                '_lock': 0,
                '_lock_timestamp': 0
            },
            upsert=True
        )

        locked_object, key = self.driver.lock_object(klass, obj_id)
        unlocked_object = self.driver.unlock_object(klass, obj_id, key)

        self.assertEqual(locked_object, unlocked_object)

        # Confirm object is intact
        final = self.driver._get_object(klass, obj_id)
        self.assertDictEqual(final, original)

    @unittest.skipIf(SKIP, REASON)
    def test_unlock_safety(self):
        """Make sure we don't do update, but do $set"""
        klass = 'workflows'
        obj_id = 1
        original = {
            "tenantId": "T1000",
            "test": obj_id,
        }
        setup_obj = copy.copy(original)
        setup_obj.update({
            "_lock": 0,
            "_id": obj_id,
        })
        self.driver.database()[klass].remove({'_id': obj_id})

        #setup unlocked workflow
        self.driver.database()[klass].find_and_modify(
            query={"_id": obj_id},
            update=setup_obj,
            fields={
                '_id': 0,
                '_lock': 0,
                '_lock_timestamp': 0
            },
            upsert=True
        )

        locked_object, key = self.driver.lock_object(klass, obj_id)
        unlocked_object = self.driver.unlock_object(klass, obj_id, key)

        self.assertEqual(locked_object, unlocked_object)

        # Confirm object is intact
        final = self.driver._get_object(klass, obj_id)
        self.assertDictEqual(final, original)

    @unittest.skipIf(SKIP, REASON)
    def test_lock_locked_deployment(self):
        klass = 'deployments'
        obj_id = 1
        self.driver.database()[klass].remove({'_id': obj_id})
        stored = {"_id": obj_id, "id": obj_id, "tenantId": "T1000",
                  "test": obj_id}
        self.driver.database()[klass].save(stored)

        self.driver.lock_object(klass, obj_id)

        with self.assertRaises(db.ObjectLockedError):
            self.driver.lock_object(klass, obj_id)

    @unittest.skipIf(SKIP, REASON)
    def test_lock_locked_workflow(self):
        klass = 'workflows'
        obj_id = 1
        self.driver.database()[klass].remove({'_id': obj_id})
        stored = {"_id": obj_id, "id": obj_id, "tenantId": "T1000",
                  "test": obj_id}
        self.driver.database()[klass].save(stored)

        self.driver.lock_object(klass, obj_id)

        with self.assertRaises(db.ObjectLockedError):
            self.driver.lock_object(klass, obj_id)

    @unittest.skipIf(SKIP, REASON)
    def test_lock_workflow_stale_lock(self):
        klass = 'workflows'
        obj_id = 1
        self.driver.database()[klass].remove({'_id': obj_id})
        lock = "test_lock"
        lock_timestamp = time.time() - 31
        stored = {"_id": obj_id, "id": obj_id, "tenantId": "T1000",
                  "test": obj_id, "_lock": lock,
                  "_lock_timestamp": lock_timestamp}
        self.driver.database()[klass].save(stored)
        # the lock is older than 30 seconds so we should be able to lock the
        # object
        _, key = self.driver.lock_workflow(obj_id)
        self.driver.unlock_workflow(obj_id, key)

    @unittest.skipIf(SKIP, REASON)
    def test_invalid_key_unlock(self):
        klass = 'workflows'
        obj_id = 1
        self.driver.database()[klass].remove({'_id': obj_id})
        stored = {"_id": obj_id, "id": obj_id, "tenantId": "T1000",
                  "test": obj_id}
        self.driver.database()[klass].save(stored)

        self.driver.lock_workflow(obj_id)

        with self.assertRaises(db.InvalidKeyError):
            self.driver.unlock_workflow(obj_id, "bad_key")

    @unittest.skipIf(SKIP, REASON)
    def test_invalid_key_lock(self):
        klass = 'workflows'
        obj_id = 1
        self.driver.database()[klass].remove({'_id': obj_id})
        stored = {"_id": obj_id, "id": obj_id, "tenantId": "T1000",
                  "test": obj_id}
        self.driver.database()[klass].save(stored)

        self.driver.lock_workflow(obj_id)

        with self.assertRaises(db.InvalidKeyError):
            self.driver.lock_workflow(obj_id, key="bad_key")

    @unittest.skipIf(SKIP, REASON)
    def test_valid_key_lock(self):
        """
        Test that we can lock an object with a valid key.
        """
        klass = 'workflows'
        obj_id = 1
        self.driver.database()[klass].remove({'_id': obj_id})
        stored = {"_id": obj_id, "id": obj_id, "tenantId": "T1000",
                  "test": obj_id}
        self.driver.database()[klass].save(stored)

        locked_obj1, key = self.driver.lock_workflow(obj_id)
        locked_obj2, key = self.driver.lock_workflow(obj_id, key=key)
        self.assertEqual(locked_obj1, locked_obj2)
        self.driver.database()[klass].remove({'_id': obj_id})

    @unittest.skipIf(SKIP, REASON)
    def test_new_safe_workflow_save(self):
        import checkmate.workflows as workflows

        workflows.DB = self.driver
        #test that a new object can be saved with the lock
        self.driver.database()['workflows'].remove({'_id': "1"})
        self.manager.safe_workflow_save("1", {"id": "yolo"}, tenant_id=2412423)

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
        self.assertListEqual(resource_list, self._get_resources(dep_id))

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
        self.assertListEqual(db_deployment['resources'], resource_ids)
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
        self.assertListEqual(db_deployment['resources'], resource_ids)
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
    def test_existing_workflow_save(self):
        import checkmate.workflows as workflows

        workflows.DB = self.driver
        #test locking an already locked workflow
        self.driver.database()['workflows'].remove({'_id': "1"})
        timestamp = time.time()
        self.driver.database()['workflows'].save({'_id': "1", "_lock": "1",
                                                  "_lock_timestamp":
                                                      timestamp})

        with self.assertRaises(db.ObjectLockedError):
            self.manager.safe_workflow_save("1", {"id": "yolo"},
                                            tenant_id=2412423)

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
        self.assertIsInstance(self.driver.lock(key, 100), db_lock.DbLock)

        self.assertRaises(db.InvalidKeyError, self.driver.unlock, "X")


    @unittest.skipIf(SKIP, REASON)
    def test_raise_if_trying_to_unlock_non_existent_key(self):
        self.assertRaises(db.InvalidKeyError, self.driver.unlock, uuid.uuid4())


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
