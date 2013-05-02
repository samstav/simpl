# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import logging
import os
import unittest2 as unittest
import time
from bottle import HTTPError

from checkmate.utils import init_console_logging
from checkmate.db.common import DatabaseTimeoutException, \
    DEFAULT_STALE_LOCK_TIMEOUT
from copy import deepcopy
import uuid

os.environ['CHECKMATE_CONNECTION_STRING'] = 'sqlite://'

from checkmate.db.sql import Deployment, Workflow
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate import db
from checkmate.utils import extract_sensitive_data


class TestDatabase(unittest.TestCase):

    def setUp(self):
        self.driver = db.get_driver(name='checkmate.db.sql.Driver', reset=True,
                                    connection_string='sqlite://')
        self.klass = Deployment
        db.sql.DEFAULT_RETRIES = 1
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
        ''' Helper method to recursively change all data elements to ints '''
        decoded_dict = {}
        for key, value in dictionary.iteritems():
            if isinstance(key, unicode):
                key = key.encode('utf-8')
                try:
                    key = int(key)
                except ValueError:
                    key = key
            if isinstance(value, unicode):
                value = value.encode('utf-8')
                if isinstance(value, int):
                    value = int(value)
            elif isinstance(value, dict):
                value = self._decode_dict(value)
            decoded_dict[key] = value
        return decoded_dict

    def test_pagination(self):
        entity = {
            'id': 1,
            'name': 'My Component',
            'credentials': ['My Secrets']
        }
        body, secrets = extract_sensitive_data(entity)
        self.driver.save_object(self.klass, entity['id'], body, secrets,
                                tenant_id='T1000')

        entity['id'] = 2
        entity['name'] = 'My Second Component'
        body, secrets = extract_sensitive_data(entity)
        self.driver.save_object(self.klass, entity['id'], body, secrets,
                                tenant_id='T1000')

        entity['id'] = 3
        entity['name'] = 'My Third Component'
        body, secrets = extract_sensitive_data(entity)
        self.driver.save_object(self.klass, entity['id'], body, secrets,
                                tenant_id='T1000')

        expected = {
            1: {
                'id': 1,
                'name': 'My Component',
                'tenantId': 'T1000'},
            2: {
                'id': 2,
                'name': 'My Second Component',
                'tenantId': 'T1000',
            }
        }
        results = self.driver.get_objects(self.klass, tenant_id='T1000',
                                          limit=2,
                                          include_total_count=False)
        results_decode = self._decode_dict(results)
        self.assertEqual(len(results_decode), 2)
        self.assertDictEqual(results_decode, expected)

        expected = {
            2: {
                'id': 2,
                'name': 'My Second Component',
                'tenantId': 'T1000',
            },
            3: {
                'id': 3,
                'name': 'My Third Component',
                'tenantId': 'T1000',
            }
        }
        results = self.driver.get_objects(self.klass, tenant_id='T1000',
                                          offset=1, limit=2,
                                          include_total_count=False)
        results_decode = self._decode_dict(results)
        self.assertEqual(len(results_decode), 2)
        self.assertDictEqual(results_decode, expected)

    def test_update_secrets(self):
        _id = str(uuid.uuid4())
        data = {
            "id": _id,
            "tenantId": "12345",
            "employee": {
                "name": "Bob",
                "title": "Mr.",
                "ssh_public_key": "rsa public key",
                "ssh_private_key": "a private key",
                "password": "password",
                "position": "left"
            },
            "server": {
                "access": {
                    "server_root_password": "password",
                    "server_privatekey": "private_key",
                    "server_public_key": "public_key"
                },
                "private_ip": "123.45.67.89",
                "public_ip": "127.0.0.1",
                "host_name": "server1"
            },
            "safe_val": "hithere",
            "secret_value": "Immasecret"
        }

        safe = {
            "id": _id,
            "tenantId": "12345",
            "employee": {
                "name": "Bob",
                "title": "Mr.",
                "ssh_public_key": "rsa public key",
                "position": "left"
            },
            "server": {
                "access": {
                    "server_public_key": "public_key"
                },
                "private_ip": "123.45.67.89",
                "public_ip": "127.0.0.1",
                "host_name": "server1"
            },
            "safe_val": "hithere",
            "secret_value": "Immasecret"
        }

        secret = {
            "employee": {
                "ssh_private_key": "a private key",
                "password": "password",
            },
            "server": {
                "access": {
                    "server_root_password": "password",
                    "server_privatekey": "private_key",
                }
            }
        }
        original = deepcopy(data)
        body, secrets = extract_sensitive_data(data)
        self.assertDictEqual(safe, self._decode_dict(body))
        self.assertDictEqual(secret, secrets)
        results = self.driver.save_object(Deployment, _id, body,
                                          secrets=secrets)
        self.assertDictEqual(results, body)
        # retrieve the object with secrets to make sure we get them correctly
        results = self.driver.get_object(Deployment, _id,
                                         with_secrets=True)
        self.assertDictEqual(original, results)
        # use the "safe" version and add a new secret
        results = self.driver.save_object(Deployment, _id, safe,
                                          secrets={"global_password":
                                                   "password secret"})
        self.assertDictEqual(safe, results)
        # update the copy with the new secret
        original['global_password'] = "password secret"
        # retrieve with secrets and make sure it was updated correctly
        results = self.driver.get_object(Deployment, _id, with_secrets=True)
        self.assertDictEqual(original, self._decode_dict(results))

    def test_workflows(self):
        entity = {
            'id': 1,
            'name': 'My Workflow',
            'credentials': ['My Secrets']
        }
        body, secrets = extract_sensitive_data(entity)
        results = self.driver.save_workflow(entity['id'], body, secrets,
                                            tenant_id='T1000')
        self.assertDictEqual(results, body)

        results = self.driver.get_workflow(entity['id'], with_secrets=True)
        entity['tenantId'] = 'T1000'  # gets added
        self.assertDictEqual(results, entity)
        self.assertIn('credentials', results)

        body['name'] = 'My Updated Workflow'
        entity['name'] = 'My Updated Workflow'
        results = self.driver.save_workflow(entity['id'], body)

        results = self.driver.get_workflow(entity['id'], with_secrets=True)
        self.assertIn('credentials', results)
        self.assertDictEqual(results, entity)

        results = self.driver.get_workflow(entity['id'], with_secrets=False)
        self.assertNotIn('credentials', results)
        body['tenantId'] = 'T1000'  # gets added
        self.assertDictEqual(results, body)

    def test_new_deployment_locking(self):
        self.driver.session.query(self.klass).filter_by(
            id=self.default_deployment['id']).delete()
        body, secrets = extract_sensitive_data(self.default_deployment)
        self.driver.save_deployment(self.default_deployment['id'],
                                    body, secrets,
                                    tenant_id='T1000')

        result = self.driver.session.query(self.klass).filter_by(
            id=self.default_deployment['id'])
        saved_deployment = result.first()
        self.assertEqual(saved_deployment.locked, 0)
        self.assertEqual(saved_deployment.body, self.default_deployment)

        self.driver.session.query(self.klass).filter_by(
            id=self.default_deployment['id']).delete()

    def test_locked_deployment(self):
        self.driver.session.query(self.klass).filter_by(
            id=self.default_deployment['id']).delete()

        body, secrets = extract_sensitive_data(self.default_deployment)
        self.driver.session.query(self.klass).filter_by(
            id=self.default_deployment['id']).update({'locked': time.time()})

        e = self.klass(id=self.default_deployment['id'], body=body,
                       tenant_id='T1000', secrets=secrets, locked=time.time())
        self.driver.session.add(e)
        self.driver.session.commit()

        with self.assertRaises(DatabaseTimeoutException):
            self.driver.save_deployment(self.default_deployment['id'], body,
                                        secrets, tenant_id='T1000')

        self.driver.session.query(self.klass).filter_by(
            id=self.default_deployment['id']).delete()

    def test_no_locked_field_deployment(self):
        self.driver.session.query(self.klass).filter_by(
            id=self.default_deployment['id']).delete()

        body, secrets = extract_sensitive_data(self.default_deployment)

        #insert without locked field
        e = self.klass(id=self.default_deployment['id'], body=body,
                       tenant_id='T1000', secrets=secrets)
        self.driver.session.add(e)
        self.driver.session.commit()

        #save, should get a locked here
        self.driver.save_deployment(self.default_deployment['id'], body,
                                    secrets, tenant_id='T1000')

        #get saved deployment
        deployment = self.driver.session.query(self.klass).filter_by(
            id=self.default_deployment['id']
        ).first()

        #check unlocked
        self.assertEquals(deployment.locked, 0)

        self.driver.session.query(self.klass).filter_by(
            id=self.default_deployment['id']).delete()

    def test_stale_lock(self):
        self.driver.session.query(self.klass).filter_by(
            id=self.default_deployment['id']).delete()

        body, secrets = extract_sensitive_data(self.default_deployment)

        #insert without locked field
        e = self.klass(id=self.default_deployment['id'], body=body,
                       tenant_id='T1000', secrets=secrets)
        self.driver.session.add(e)
        self.driver.session.commit()

        #save, should get a _locked here
        self.driver.save_deployment(self.default_deployment['id'], body,
                                    secrets, tenant_id='T1000')

        #set timestamp to a stale time
        timeout = time.time()
        self.driver.session.query(self.klass).filter_by(
            id=self.default_deployment['id']).update({
                'locked': timeout - DEFAULT_STALE_LOCK_TIMEOUT})
        self.driver.session.commit()

        #test remove stale lock
        self.driver.save_deployment(self.default_deployment['id'], body,
                                    secrets, tenant_id='T1000')

        #get saved deployment
        deployment = self.driver.session.query(self.klass).filter_by(
            id=self.default_deployment['id']).first()

        #check for unlocked
        self.assertEquals(deployment.locked, 0)

        self.driver.session.query(self.klass).filter_by(
            id=self.default_deployment['id']).delete()

    def test_driver_creation(self):
        driver = db.get_driver(connection_string='sqlite://')
        self.assertEquals(driver.connection_string, 'sqlite://')
        self.assertEquals(driver.__class__.__name__, 'Driver')

    def test_driver_creation_multiple(self):
        driver1 = db.get_driver(connection_string='sqlite://')
        driver2 = db.get_driver(connection_string='mongodb://fake')
        self.assertNotEqual(driver1, driver2)
        self.assertEquals(driver1.connection_string, 'sqlite://')
        self.assertEquals(driver2.connection_string, 'mongodb://fake')

    def test_driver_creation_multiple_same_class(self):
        driver1 = db.get_driver(connection_string='mongodb://fake1')
        driver2 = db.get_driver(connection_string='mongodb://fake2')
        self.assertNotEqual(driver1, driver2)

    def test_lock_existing_object(self):
        klass = Workflow
        obj_id = 1
        filter_obj = (self.driver
                          .session
                          .query(klass)
                          .filter_by(id=obj_id)
                          .first())
        if filter_obj:
            filter_obj.delete()
        self.driver.save_object(klass, obj_id, {"id": obj_id, "test": obj_id},
                                tenant_id='T1000')

        _, key = self.driver.lock_object(klass, obj_id)
        #was a key generated?
        self.assertTrue(key)
        stored_object = self.driver.session.query(klass).filter_by(
            id=obj_id).first()

        #was the key stored correctly?
        self.assertEqual(key, stored_object.lock)
        #was a _lock_timestamp generated
        self.assertTrue(stored_object.lock_timestamp > 0)

    def delete(self, klass, obj_id):
        filter_obj = (self.driver
                          .session
                          .query(klass)
                          .filter_by(id=obj_id)
                          .first())
        if filter_obj:
            filter_obj.delete()

    def test_unlock_existing_object(self):
        klass = Workflow
        obj_id = 1
        original = {
            "test": obj_id
        }
        self.delete(klass, obj_id)

        #setup unlocked workflow
        self.driver.session.add(klass(id=obj_id,
                                body=original,
                                tenant_id='T1000',
                                lock=0))

        locked_object, key = self.driver.lock_object(klass, obj_id)
        unlocked_object = self.driver.unlock_object(klass, obj_id, key)

        self.assertEqual(locked_object, unlocked_object)

        # Confirm object is intact
        final = self.driver.get_object(klass, obj_id)
        original['tenantId'] = 'T1000'
        self.assertDictEqual(final, original)

    def test_unlock_safety(self):
        '''Make sure we don't do update, but do $set'''
        klass = Workflow
        obj_id = 1
        original = {
            "test": obj_id
        }
        self.delete(klass, obj_id)

        #setup unlocked workflow
        self.driver.session.add(klass(id=obj_id,
                                      body=original,
                                      tenant_id='T1000',
                                      lock=0,
                                      lock_timestamp=0))
        original['tenantId'] = 'T1000'

        locked_object, key = self.driver.lock_object(klass, obj_id)
        unlocked_object = self.driver.unlock_object(klass, obj_id, key)

        self.assertEqual(locked_object, unlocked_object)

        # Confirm object is intact
        final = self.driver.get_object(klass, obj_id)
        self.assertDictEqual(final, original)

    def test_lock_locked_object(self):
        klass = Workflow
        obj_id = 1
        self.delete(klass, obj_id)
        self.driver.session.add(klass(id=obj_id,
                                      body={'test': obj_id},
                                      tenant_id='T1000',
                                      lock=0,
                                      lock_timestamp=0))

        self.driver.lock_object(klass, obj_id)

        with self.assertRaises(db.ObjectLockedError):
            self.driver.lock_object(klass, obj_id)

    def test_lock_workflow_stale_lock(self):
        klass = Workflow
        obj_id = 1
        self.delete(klass, obj_id)
        lock_timestamp = time.time() - 6

        self.driver.session.add(klass(id=obj_id,
                                      body={'test': obj_id},
                                      tenant_id='T1000',
                                      lock="test_lock",
                                      lock_timestamp=lock_timestamp))

        # the lock is older than 5 seconds so we should be able to lock the
        # object
        _, key = self.driver.lock_workflow(obj_id)
        self.driver.unlock_workflow(obj_id, key)

    def test_invalid_key_unlock(self):
        klass = Workflow
        obj_id = 1
        self.delete(klass, obj_id)
        self.driver.session.add(klass(id=obj_id,
                                body={'test': obj_id},
                                tenant_id='T1000',
                                lock=0,
                                lock_timestamp=time.time()))

        self.driver.lock_workflow(obj_id)

        with self.assertRaises(db.InvalidKeyError):
            self.driver.unlock_workflow(obj_id, "bad_key")

    def test_invalid_key_lock(self):
        klass = Workflow
        obj_id = 1
        self.delete(klass, obj_id)
        self.driver.session.add(klass(id=obj_id,
                                      body={'test': obj_id},
                                      tenant_id='T1000',
                                      lock=0,
                                      lock_timestamp=0))
        self.driver.lock_workflow(obj_id)

        with self.assertRaises(db.InvalidKeyError):
            self.driver.lock_workflow(obj_id, key="bad_key")

    def test_valid_key_lock(self):
        """
        Test that we can lock an object with a valid key.
        """
        klass = Workflow
        obj_id = 1
        self.delete(klass, obj_id)
        self.driver.session.add(klass(id=obj_id,
                                body={'test': obj_id},
                                tenant_id='T1000',
                                lock=0,
                                lock_timestamp=0))

        self.driver.session.commit()
        locked_obj1, key = self.driver.lock_workflow(obj_id)
        locked_obj2, key = self.driver.lock_workflow(obj_id, key=key)
        self.assertEqual(locked_obj1, locked_obj2)

    def test_new_safe_workflow_save(self):
        klass = Workflow
        obj_id = 1
        import checkmate.workflows as workflows
        workflows.DB = self.driver
        #test that a new object can be saved with the lock
        self.delete(klass, obj_id)
        workflows.safe_workflow_save(obj_id,
                                     {"id": "yolo"},
                                     tenant_id=2412423,
                                     driver=self.driver)

    def test_existing_workflow_save(self):
        klass = Workflow
        obj_id = 1
        import checkmate.workflows as workflows
        workflows.DB = self.driver
        #test locking an already locked workflow
        self.delete(klass, obj_id)
        timestamp = time.time()
        self.driver.session.add(klass(id=obj_id,
                                      body={'test': obj_id},
                                      tenant_id='T1000',
                                      lock="1",
                                      lock_timestamp=timestamp))

        with self.assertRaises(HTTPError):
            workflows.safe_workflow_save(obj_id,
                                         {"id": "yolo"},
                                         tenant_id=2412423,
                                         driver=self.driver)


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    sys.path.insert(1, os.path.join(sys.path[0], '../..'))
    from tests.utils import run_with_params
    run_with_params(sys.argv[:])
