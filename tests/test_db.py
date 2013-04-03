#!/usr/bin/env python
import logging
import os
import unittest2 as unittest

from checkmate.utils import init_console_logging
from checkmate.db.common import DatabaseTimeoutException
from copy import deepcopy
import uuid

os.environ['CHECKMATE_CONNECTION_STRING'] = 'sqlite://'

from checkmate.db.sql import Deployment, Workflow
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate import db
from checkmate.utils import extract_sensitive_data


class TestDatabase(unittest.TestCase):
    """ Test Database code """

    def setUp(self):
        self.driver = db.get_driver('checkmate.db.sql.Driver', reset=True)
        self.klass = Deployment
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
                except Exception:
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
faweklfjawe
        entity = {'id': 1,
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

        expected = {1:
                      {'id': 1,
                       'name': 'My Component',
                       'tenantId': 'T1000'},
                    2: 
                      {'id': 2,
                       'name': 'My Second Component',
                       'tenantId': 'T1000'}}
        results = self.driver.get_objects(self.klass, tenant_id='T1000', limit=2)
        results_decode = self._decode_dict(results)
        self.assertEqual(len(results_decode), 2)
        self.assertDictEqual(results_decode, expected)

        expected = {2:
                      {'id': 2,
                       'name': 'My Second Component',
                       'tenantId': 'T1000'},
                    3: 
                      {'id': 3,
                       'name': 'My Third Component',
                       'tenantId': 'T1000'}}
        results = self.driver.get_objects(self.klass, tenant_id='T1000',
                                          offset=1, limit=2)
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
                            secrets={"global_password": "password secret"})
        self.assertDictEqual(safe, results)
        # update the copy with the new secret
        original['global_password'] = "password secret"
        # retrieve with secrets and make sure it was updated correctly
        results = self.driver.get_object(Deployment, _id, with_secrets=True)
        self.assertDictEqual(original, self._decode_dict(results))

    def test_components(self):
        entity = {'id': 1,
                  'name': 'My Component',
                  'credentials': ['My Secrets']
                 }
        body, secrets = extract_sensitive_data(entity)
        results = self.driver.save_component(entity['id'], body, secrets,
            tenant_id='T1000')
        self.assertDictEqual(results, body)

        results = self.driver.get_component(entity['id'], with_secrets=True)
        entity['tenantId'] = 'T1000'  # gets added
        self.assertDictEqual(results, entity)
        self.assertIn('credentials', results)

        body['name'] = 'My Updated Component'
        entity['name'] = 'My Updated Component'
        results = self.driver.save_component(entity['id'], body)

        results = self.driver.get_component(entity['id'], with_secrets=True)
        self.assertIn('credentials', results)
        self.assertDictEqual(results, entity)

        results = self.driver.get_component(entity['id'], with_secrets=False)
        self.assertNotIn('credentials', results)
        body['tenantId'] = 'T1000'  # gets added
        self.assertDictEqual(results, body)

    def test_new_deployment_locking(self):
        db.sql.Session.query(self.klass).filter_by(
            id=self.default_deployment['id']).delete()
        body, secrets = extract_sensitive_data(self.default_deployment)
        results = self.driver.save_deployment(self.default_deployment['id'], body, secrets,
        tenant_id='T1000')

        result = db.sql.Session.query(self.klass).filter_by(id=self.default_deployment['id'])
        saved_deployment = result.first()
        self.assertEqual(saved_deployment.locked, 0)
        self.assertEqual(saved_deployment.body, self.default_deployment)
        
        db.sql.Session.query(self.klass).filter_by(
            id=self.default_deployment['id']).delete()
  

    def test_locked_deployment(self):
        db.sql.Session.query(self.klass).filter_by(
            id=self.default_deployment['id']).delete()
 
        body, secrets = extract_sensitive_data(self.default_deployment)
        e = self.klass(id=self.default_deployment['id'], body=body, secrets=secrets,
        tenant_id='T1000', locked=1)

        db.sql.Session.add(e)
        db.sql.Session.commit()
        db.sql.DEFAULT_RETRIES = 1

        with self.assertRaises(DatabaseTimeoutException):
            self.driver.save_deployment(self.default_deployment['id'],body, secrets, tenant_id='T1000')
  
        db.sql.Session.query(self.klass).filter_by(
            id=self.default_deployment['id']).delete()
  


if __name__ == '__main__':
    # Run tests. Handle our parameters seprately
    import sys
    args = sys.argv[:]
    # Our --debug means --verbose for unittest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
