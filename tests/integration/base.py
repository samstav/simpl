# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''

Base class for testing database drivers

This performs a full suite of tests on a driver to make sure it conforms to the
expected interface.

To use this:

from base import TestDBDriver

class TestMyDriver(TestDBDriver):
    connection_string = 'myDb://in-memory'  # or however your driver works

    def setUp(self):
        TestDBDriver.setUp(self)  # don't forget to call superclass

    def test_your_extra_tests(self):
        pass


'''
import copy
import uuid

import unittest2 as unittest
from checkmate import db, utils


class DBDriverTests(unittest.TestCase):
    '''Test Any Driver'''

    connection_string = None  # meant to be overridden

    def setUp(self):
        self.maxDiff = None
        if self.connection_string:
            self.driver = db.get_driver(
                connection_string=self.connection_string)

    def test_instantiation(self):
        self.assertEqual(self.driver.connection_string, self.connection_string)

    def test_update_secrets(self):
        _id = uuid.uuid4().hex[0:8]
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
        original = copy.deepcopy(data)
        body, secrets = utils.extract_sensitive_data(data)
        self.assertDictEqual(safe, body)
        self.assertDictEqual(secret, secrets)
        results = self.driver.save_deployment(_id, body, secrets=secrets)
        self.assertDictEqual(results, body)
        # retrieve the object with secrets to make sure we get them correctly
        results = self.driver.get_deployment(_id, with_secrets=True)
        self.assertDictEqual(original, results)
        # use the "safe" version and add a new secret
        results = self.driver.save_deployment(_id, safe,
                                              secrets={
                                                  "global_password":
                                                  "password secret"
                                              })
        self.assertDictEqual(safe, results)
        # update the copy with the new secret
        original['global_password'] = "password secret"
        # retrieve with secrets and make sure it was updated correctly
        results = self.driver.get_deployment(_id, with_secrets=True)
        self.assertDictEqual(original, results)

    def test_workflows(self):
        _id = uuid.uuid4().hex[0:8]
        entity = {
            u'id': _id,
            u'name': u'My Workflow',
            u'credentials': [u'My Secrets']
        }
        body, secrets = utils.extract_sensitive_data(entity)
        results = self.driver.save_workflow(entity['id'], body, secrets,
                                            tenant_id='T1000')
        self.assertDictEqual(results, body)

        results = self.driver.get_workflow(entity['id'], with_secrets=True)
        entity['tenantId'] = u'T1000'  # gets added
        self.assertDictEqual(results, entity)
        self.assertIn('credentials', results)

        body[u'name'] = u'My Updated Workflow'
        entity[u'name'] = u'My Updated Workflow'
        results = self.driver.save_workflow(entity[u'id'], body)

        results = self.driver.get_workflow(entity[u'id'], with_secrets=True)
        self.assertIn(u'credentials', results)
        self.assertDictEqual(results, entity)

        results = self.driver.get_workflow(entity[u'id'], with_secrets=False)
        self.assertNotIn(u'credentials', results)
        body[u'tenantId'] = u'T1000'  # gets added
        self.assertDictEqual(results, body)

    def test_save_get_delete_object_with_defaults(self):
        '''We are really testing object, but using deployment so that the
        test works regardless of driver implementation
        '''
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234'}
        )
        self.assertEquals(
            {'id': '1234', 'tenantId': 'T3'},
            self.driver.get_deployment('1234')
        )
        self.driver.delete_deployment('1234', tenant_id='T3')
        self.assertEquals(None, self.driver.get_deployment('1234'))

    def test_save_get_delete_object_with_secrets(self):
        '''We are really testing object, but using deployment so that the
        test works regardless of driver implementation
        '''
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234'},
            secrets={'secret': 'SHHH!!!'}
        )
        self.assertEquals(
            {'id': '1234', 'tenantId': 'T3', 'secret': 'SHHH!!!'},
            self.driver.get_deployment('1234', with_secrets=True)
        )
        self.assertEquals(
            {'id': '1234', 'tenantId': 'T3'},
            self.driver.get_deployment('1234', with_secrets=False)
        )
        self.driver.delete_deployment('1234', 'T3')
        self.assertEquals(None, self.driver.get_deployment('deployments', '1234'))

    def test_save_object_with_merge(self):
        '''We are really testing object, but using deployment so that the
        test works regardless of driver implementation
        '''

        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'old': 'blarp'}
        )

        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'new': 'blerg'},
            partial=True  # merge_existing in _save_object
        )

        self.assertEquals(
            {'id': '1234', 'tenantId': 'T3', 'old': 'blarp', 'new': 'blerg'},
            self.driver.get_deployment('1234')
        )

    def test_save_object_with_overwrite(self):
        '''We are really testing object, but using deployment so that the
        test works regardless of driver implementation
        '''

        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'old': 'blarp'}
        )

        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'new': 'blerg'},
            partial=False  # merge_existing in _save_object
        )

        self.assertEquals(
            {'id': '1234', 'tenantId': 'T3', 'new': 'blerg'},
            self.driver.get_deployment('1234')
        )


    def test_deleting_locked_object_not_allowed(self):
        pass  # IMPLEMENT ME!!!

    def test_deleting_with_wrong_tenant_id_not_allowed(self):
        pass  # IMPLEMENT ME!!!

    def test_get_objects_with_defaults(self):
        pass  # IMPLEMENT ME!!!

    def test_get_objects_with_secrets(self):
        pass  # IMPLEMENT ME!!!

    def test_get_objects_with_offset(self):
        pass  # IMPLEMENT ME!!!

    def test_get_objects_with_limit(self):
        pass  # IMPLEMENT ME!!!

    def test_get_objects_with_count(self):
        pass  # IMPLEMENT ME!!!

    def test_get_deployments_omitting_deleted(self):
        pass  # IMPLEMENT ME!!!

    def test_get_deployments_including_deleted(self):
        pass  # IMPLEMENT ME!!!


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
