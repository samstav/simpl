# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import copy
import logging
import unittest2 as unittest
import uuid
import time
from bottle import HTTPError

try:
    from mongobox import MongoBox
    SKIP = False
    REASON = None
except ImportError as exc:
    SKIP = True
    REASON = "'mongobox' not installed: %s" % exc
    MongoBox = object

from checkmate import db
from checkmate.db.common import ObjectLockedError, InvalidKeyError
from checkmate.utils import extract_sensitive_data
from checkmate.workflows import safe_workflow_save

LOG = logging.getLogger(__name__)


class TestDatabase(unittest.TestCase):
    """ Test Mongo Database code """

    #pylint: disable=W0603
    @classmethod
    def setUpClass(cls):
        '''Fire up a sandboxed mongodb instance'''
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
        '''Stop the sanboxed mongodb instance'''
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
        self.default_deployment = {
            'id': 'test',
            'name': 'test',
            'inputs': {},
            'includes': {},
            'resources': {},
            'workflow': "abcdef",
            'status': "NEW",
            'created': "yesterday",
            'tenantId': "T1000",
            'blueprint': {
                'name': 'test bp',
            },
            'environment': {
                'name': 'environment',
                'providers': {},
            },
        }

    def _decode_dict(self, dictionary):
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
        self.assertEqual(len(self.driver._get_objects('foobars')), 0)

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
        results = self.driver._get_object(self.collection_name, entity['id'],
                                         with_secrets=True)
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

        self.assertIn('id', results[1])
        self.assertEqual(results[1]['id'], 1)
        self.assertDictEqual(results, expected_result_body)

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
        self.assertEqual(len(results), 2)
        self.assertDictEqual(results, expected)

        results = self.driver._get_objects(self.collection_name,
                                           tenant_id='T1000',
                                           with_secrets=False, offset=1,
                                           limit=2,
                                           with_count=False)
        expected = {
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
        self.assertDictEqual(results,
                             {hex_id: {"id": hex_id, 'tenantId': 'T1000'}})
        self.assertNotIn('_id', results, "Backend field '_id' should not be "
                         "exposed outside of driver")

    @unittest.skipIf(SKIP, REASON)
    def test_no_id_in_body(self):
        hex_id = uuid.uuid4().hex
        self.assertRaises(Exception, self.driver._save_object, hex_id, {}, None,
                          tenant_id='T1000')

    @unittest.skipIf(SKIP, REASON)
    def test_multiple_objects(self):
        expected = {}
        for i in range(1, 5):
            expected[i] = dict(id=i, tenantId='T1000')
            self.driver._save_object(self.collection_name, i, dict(id=i), None,
                                     tenant_id='T1000')
        unicode_results = self.driver._get_objects(self.collection_name,
                                                   with_count=False)
        results = self._decode_dict(unicode_results)
        self.assertDictEqual(results, expected)
        for i in range(1, 5):
            self.assertIn(i, results)
            self.assertNotIn('_id', results[i])
            self.assertEqual(results[i]['id'], i)

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

    def test_save_deployment_fails_if_locked(self):
        klass = 'deployments'
        obj_id = 1
        self.driver.database()[klass].remove({"id": obj_id})
        self.driver.save_deployment(obj_id,
                                    {"id": obj_id, "test": obj_id},
                                    tenant_id="T1000",
                                    partial=False)
        locked_object, _ = self.driver.lock_object(klass, obj_id)
        with self.assertRaises(ObjectLockedError):
            self.driver.save_deployment(obj_id,
                                        {"id": obj_id, "test": obj_id},
                                        tenant_id="T1000",
                                        partial=False)

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
        '''Make sure we don't do update, but do $set'''
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

        with self.assertRaises(ObjectLockedError):
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

        with self.assertRaises(ObjectLockedError):
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

        with self.assertRaises(InvalidKeyError):
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

        with self.assertRaises(InvalidKeyError):
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
        safe_workflow_save("1", {"id": "yolo"}, tenant_id=2412423,
                           driver=self.driver)

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

        with self.assertRaises(HTTPError):
            safe_workflow_save("1", {"id": "yolo"}, tenant_id=2412423,
                               driver=self.driver)


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
