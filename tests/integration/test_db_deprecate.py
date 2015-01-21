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
import mock
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

        get_driver_patcher = mock.patch.object(manager.db, 'get_driver')
        mock_get_driver = get_driver_patcher.start()
        mock_get_driver.return_value = self.driver
        self.addCleanup(get_driver_patcher.stop)

        self.manager = manager.Manager()
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
        self.assertEqual(deployment.locked, 0)

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
        self.assertEqual(deployment.locked, 0)

        self.driver.session.query(self.klass).filter_by(
            id=self.default_deployment['id']).delete()

    def delete(self, klass, obj_id):
        """Helper method to delete a filter object."""
        filter_obj = (self.driver
                          .session
                          .query(klass)
                          .filter_by(id=obj_id)
                          .first())
        if filter_obj:
            filter_obj.delete()


class TestDriverCreation(unittest.TestCase):
    def test_driver_creation(self):
        driver = db.get_driver(connection_string='sqlite://')
        self.assertEqual(driver.connection_string, 'sqlite://')
        self.assertEqual(driver.__class__.__name__, 'Driver')

    def test_driver_creation_multiple(self):
        driver1 = db.get_driver(connection_string='sqlite://')
        driver2 = db.get_driver(connection_string='mongodb://fake')
        self.assertNotEqual(driver1, driver2)
        self.assertEqual(driver1.connection_string, 'sqlite://')
        self.assertEqual(driver2.connection_string, 'mongodb://fake')

    def test_create_multiple_same_class(self):
        driver1 = db.get_driver(connection_string='mongodb://fake1')
        driver2 = db.get_driver(connection_string='mongodb://fake2')
        self.assertNotEqual(driver1, driver2)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
