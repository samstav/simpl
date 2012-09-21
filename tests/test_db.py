#!/usr/bin/env python
import bottle
import json
import os
import unittest2 as unittest
from checkmate.deployments import Deployment
from uuid import UUID
import uuid
import collections

os.environ['CHECKMATE_CONNECTION_STRING'] = 'sqlite://'
from checkmate import db
from checkmate.utils import extract_sensitive_data


class TestDatabase(unittest.TestCase):
    """ Test Database code """

    def setUp(self):
        self.driver = db.get_driver('checkmate.db.sql.Driver')

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
    unittest.main(verbosity=2)
