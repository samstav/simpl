#!/usr/bin/env python
import logging
import os
import unittest2 as unittest
from checkmate.deployments import Deployment
from uuid import UUID
import uuid
import collections

from checkmate.utils import init_console_logging
from copy import deepcopy
import uuid

os.environ['CHECKMATE_CONNECTION_STRING'] = 'sqlite://'

from checkmate.db.sql import Deployment
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate import db
from checkmate.utils import extract_sensitive_data


class TestDatabase(unittest.TestCase):
    """ Test Database code """

    def setUp(self):
        self.driver = db.get_driver('checkmate.db.sql.Driver', reset=True)

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
    
    def test_deployments(self):
        deployment = Deployment(
        {
          'includes': { 
            'components': {
                'widget': {
                    'id': "widget",
                    'is': "application",
                    'requires':{
                        'compute':{
                            'relation': "host"
                        }
                    },
                    'provides': [
                        {'application': "foo"}
                    ]
                }
            }
          },
          'inputs':{
              'services':{
                  'testservice': {
                      'application':{
                          'count': 3
                      },
                      'compute': {
                          'os': 'mac',
                          'size': 2
                      }
                  }
              }
          },
          'blueprint':{
             'services':{
                'testservice':{
                    'instances':[
                       '0',
                       '1',
                       '2'
                    ],
                   'component':{
                       'type':'widget',
                       'interface':'foo',
                       'id':'a-widget'
                   }
                }
             },
             'options':{
                'instances':{
                    'required': True,
                    'type': 'number',
                    'default': 1,
                    'description': 'Number of instances to deploy',
                    'constrains': [{ 'service': 'testservice', 'resource_type': 'application', 'setting': 'count', 'scalable': True}],
                    'constraints': { 'min': 1, 'max': 4}
                },
                'size':{
                    'required': True,
                    'type': 'select',
                    'options': [{'value':1, 'name':'tiny'}, {'value':2, 'name':'small'}, {'value':3, 'name':'big'}, 
                                {'value':4, 'name':'bigger'}, {'value':5, 'name':'biggest'}],
                    'default': 'small',
                    'constrains': [{'service': 'testservice', 'resource_type': 'compute', 'setting': 'size', 'scalable': True}]
                },
                'os':{
                    'required': True,
                    'type': 'select',
                    'options': [{'value':'win2008', 'name':'windows'}, {'value': 'linux', 'name':'linux'}, {'name':'macOSXServer','value':'mac'}, 
                                {'value':'mosix', 'name':'mosix'}],
                    'default': 'moxix',
                    'constrains': [{'service': 'testservice', 'resource_type': 'compute', 'setting': 'image'}]
                }
              }
           }
           # omitted environment/providers for simplicity as this is just for testing the persistence part
        })
        
        # save the deployment
        _id = uuid.uuid4().hex
        deployment[id] = _id
        body, secrets = extract_sensitive_data(deployment)
        saved = self.driver.save_deployment(_id, body, secrets, tenant_id='T1000')
        self.assertTrue(saved, "nothing returned from save call")
        self.assertDictEqual(body._data, saved, "Saved data not equal")
        # retrieve it
        saved_deployment = self.driver.get_deployment(_id, with_secrets=True)
        del saved_deployment['tenantId']
        saved_deployment = Deployment(saved_deployment)
        self.assertIsNotNone(saved_deployment, "Deployment not found")
        # change it
        self.assertTrue("application" in saved_deployment.inputs().get("services", {}).get("testservice", {}), "no application setting in saved version")
        saved_deployment.set_setting("count", service_name="testservice", resource_type="application")
        self.assertFalse("application" in saved_deployment.inputs().get("services", {}).get("testservice", {}), "no application setting in saved version")
        body, secrets = extract_sensitive_data(saved_deployment)
        saved = self.driver.save_deployment(_id, body, secrets, tenant_id='T1000')
        # verify changes are saved
        saved_deployment = self.driver.get_deployment(_id)
        self.assertIsNotNone(saved_deployment, "Deployment not found")
        self.assertFalse("application" in saved_deployment.get("inputs",{}).get("services", {}).get("testservice", {}), "application not removed in saved version")


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
