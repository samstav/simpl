# pylint: disable=W0212

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

"""Base tests for all Database drivers."""
import logging
import os
import time
import unittest

from checkmate import db
from checkmate import utils
from checkmate.workflows import manager

LOG = logging.getLogger(__name__)
os.environ['CHECKMATE_CONNECTION_STRING'] = 'sqlite://'


class TestDatabase(unittest.TestCase):

    def setUp(self):
        self.driver = db.get_driver(name='checkmate.db.sql.Driver', reset=True,
                                    connection_string='sqlite://')
        self.manager = manager.Manager({'default': self.driver})
        self.klass = db.sql.Deployment
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
        """Helper method to recursively change all data elements to ints."""
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
            'status': 'NEW',
            'credentials': ['My Secrets']
        }
        body, secrets = utils.extract_sensitive_data(entity)
        self.driver._save_object(
            self.klass,
            entity['id'],
            body,
            secrets,
            tenant_id='T1000'
        )
        entity['id'] = 2
        entity['name'] = 'My Second Component'
        entity['status'] = 'NEW'
        body, secrets = utils.extract_sensitive_data(entity)
        self.driver._save_object(
            self.klass,
            entity['id'],
            body,
            secrets,
            tenant_id='T1000'
        )
        entity['id'] = 3
        entity['name'] = 'My Third Component'
        entity['status'] = 'NEW'
        body, secrets = utils.extract_sensitive_data(entity)
        self.driver._save_object(
            self.klass,
            entity['id'],
            body,
            secrets,
            tenant_id='T1000'
        )
        expected = {
            '_links': {},
            'results': {
                1: {
                    'id': 1,
                    'name': 'My Component',
                    'tenantId': 'T1000',
                    'status': 'NEW'
                },
                2: {
                    'id': 2,
                    'name': 'My Second Component',
                    'tenantId': 'T1000',
                    'status': 'NEW'
                }
            }
        }
        results = self.driver._get_objects(
            self.klass,
            tenant_id='T1000',
            limit=2,
            with_count=False
        )
        results_decode = self._decode_dict(results)
        self.assertEqual(len(results_decode), 2)
        self.assertDictEqual(results_decode, expected)

        expected = {
            '_links': {},
            'results': {
                2: {
                    'id': 2,
                    'name': 'My Second Component',
                    'tenantId': 'T1000',
                    'status': 'NEW'
                },
                3: {
                    'id': 3,
                    'name': 'My Third Component',
                    'tenantId': 'T1000',
                    'status': 'NEW'
                }
            }
        }
        results = self.driver._get_objects(
            self.klass,
            tenant_id='T1000',
            offset=1,
            limit=2,
            with_count=False
        )
        results_decode = self._decode_dict(results)
        self.assertEqual(len(results_decode), 2)
        self.assertDictEqual(results_decode, expected)

    def test_new_deployment_locking(self):
        self.driver.session.query(self.klass).filter_by(
            id=self.default_deployment['id']).delete()
        body, secrets = utils.extract_sensitive_data(self.default_deployment)
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

        body, secrets = utils.extract_sensitive_data(self.default_deployment)
        self.driver.session.query(self.klass).filter_by(
            id=self.default_deployment['id']).update({'locked': time.time()})

        data_to_write = self.klass(id=self.default_deployment['id'], body=body,
                                   tenant_id='T1000', secrets=secrets,
                                   locked=time.time())
        self.driver.session.add(data_to_write)
        self.driver.session.commit()

        with self.assertRaises(db.common.DatabaseTimeoutException):
            self.driver.save_deployment(self.default_deployment['id'], body,
                                        secrets, tenant_id='T1000')

        self.driver.session.query(self.klass).filter_by(
            id=self.default_deployment['id']).delete()

    def test_no_locked_field_deployment(self):
        self.driver.session.query(self.klass).filter_by(
            id=self.default_deployment['id']).delete()

        body, secrets = utils.extract_sensitive_data(self.default_deployment)

        #insert without locked field
        data_to_write = self.klass(id=self.default_deployment['id'], body=body,
                                   tenant_id='T1000', secrets=secrets)
        self.driver.session.add(data_to_write)
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

        body, secrets = utils.extract_sensitive_data(self.default_deployment)

        #insert without locked field
        data_to_write = self.klass(id=self.default_deployment['id'], body=body,
                                   tenant_id='T1000', secrets=secrets)
        self.driver.session.add(data_to_write)
        self.driver.session.commit()

        #save, should get a _locked here
        self.driver.save_deployment(self.default_deployment['id'], body,
                                    secrets, tenant_id='T1000')

        #set timestamp to a stale time
        timeout = time.time()
        self.driver.session.query(self.klass).filter_by(
            id=self.default_deployment['id']).update({
                'locked': timeout - db.common.DEFAULT_STALE_LOCK_TIMEOUT})
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

    def test_create_multiple_same_class(self):
        driver1 = db.get_driver(connection_string='mongodb://fake1')
        driver2 = db.get_driver(connection_string='mongodb://fake2')
        self.assertNotEqual(driver1, driver2)

    def test_lock_existing_object(self):
        klass = db.sql.Workflow
        obj_id = 1
        filter_obj = (self.driver
                          .session
                          .query(klass)
                          .filter_by(id=obj_id)
                          .first())
        if filter_obj:
            filter_obj.delete()
        self.driver._save_object(
            klass,
            obj_id,
            {"id": obj_id, "test": obj_id},
            tenant_id='T1000'
        )
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
        """Helper method to delete a filter object."""
        filter_obj = (self.driver
                          .session
                          .query(klass)
                          .filter_by(id=obj_id)
                          .first())
        if filter_obj:
            filter_obj.delete()

    def test_unlock_existing_object(self):
        klass = db.sql.Workflow
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
        final = self.driver._get_object(klass, obj_id)
        original['tenantId'] = 'T1000'
        self.assertDictEqual(final, original)

    def test_unlock_safety(self):
        klass = db.sql.Workflow
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
        final = self.driver._get_object(klass, obj_id)
        self.assertDictEqual(final, original)

    def test_lock_locked_object(self):
        klass = db.sql.Workflow
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
        klass = db.sql.Workflow
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
        klass = db.sql.Workflow
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
        klass = db.sql.Workflow
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
        klass = db.sql.Workflow
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
        klass = db.sql.Workflow
        obj_id = 1
        import checkmate.workflows as workflows
        workflows.DB = self.driver
        #test that a new object can be saved with the lock
        self.delete(klass, obj_id)
        self.manager.safe_workflow_save(obj_id, {"id": "yolo"},
                                        tenant_id=2412423)

    def test_existing_workflow_save(self):
        klass = db.sql.Workflow
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

        with self.assertRaises(db.ObjectLockedError):
            self.manager.safe_workflow_save(obj_id, {"id": "yolo"},
                                            tenant_id=2412423)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
