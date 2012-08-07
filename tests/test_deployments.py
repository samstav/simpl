#!/usr/bin/env python
import copy
import unittest2 as unittest
import checkmate
import mox

from checkmate.deployments import Deployment, plan, scale_deployment
from checkmate.exceptions import CheckmateValidationException
from checkmate.providers.base import PROVIDER_CLASSES, ProviderBase
from checkmate.server import RequestContext
from checkmate.utils import yaml_to_dict
from bottle import HTTPError, BaseRequest
import bottle
from bottle import Request, LocalRequest
import json



class TestDeployments(unittest.TestCase):
    def test_parser(self):
        """Test the parser works on a minimal deployment"""
        deployment = {
                'id': 'test',
                'blueprint': {
                    'name': 'test bp',
                    },
                'environment': {
                    'name': 'environment',
                    'providers': {},
                    },
                }
        original = copy.copy(deployment)
        parsed = plan(Deployment(deployment), RequestContext())
        del parsed['status']  # we expect this to get added
        del parsed['created']  # we expect this to get added
        self.assertDictEqual(original, parsed.__dict__())

    def test_resource_generator(self):
        """Test the parser generates the right number of resources"""
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    back:
                      component: &widget
                        id: widget
                        type: widget
                        interface: foo
                    front:
                      component: *widget
                      relations:
                        middle: foo
                    middle:
                      component: *widget
                      relations:
                        back: foo
                environment:
                  name: environment
                  providers:
                    base:
                      provides:
                      - widget: foo
                      vendor: test
                      catalog:
                        widget:
                          small_widget:
                            is: widget
                            provides:
                            - widget: foo
                          big_widget:
                            is: widget
                            provides:
                            - widget: bar
                    common:
                      credentials:
                      - password: secret
                        username: tester
                inputs:
                  services:
                    middle:
                      widget:
                        count: 4
            """))

        PROVIDER_CLASSES['test.base'] = ProviderBase

        parsed = plan(deployment, RequestContext())
        services = parsed['blueprint']['services']
        self.assertEqual(len(services['front']['instances']), 1)
        self.assertEqual(len(services['middle']['instances']), 4)
        self.assertEqual(len(services['back']['instances']), 1)
        #import json
        #print json.dumps(parsed, indent=2)

class TestComponentSearch(unittest.TestCase):
    """ Test code that finds components """
    def test_component_find_by_type(self):
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    one:
                      component:
                        type: widget
                environment:
                  name: environment
                  providers:
                    base:
                      provides:
                      - widget: foo
                      vendor: test
                      catalog:
                        widget:
                          small_widget:
                            is: widget
                            provides:
                            - widget: foo
            """))
        PROVIDER_CLASSES['test.base'] = ProviderBase
        plan(deployment, RequestContext())
        self.assertEquals(deployment['resources'].values()[0]['component'],
                'small_widget')

    def test_component_find_by_type_and_interface(self):
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    one:
                      component:
                        type: widget
                        interface: foo
                    two:
                      component:
                        type: widget
                        interface: bar
                environment:
                  name: environment
                  providers:
                    base:
                      provides:
                      - widget: foo
                      - widget: bar
                      vendor: test
                      catalog:
                        widget:
                          small_widget:
                            is: widget
                            provides:
                            - widget: foo
                          big_widget:
                            is: widget
                            provides:
                            - widget: bar
            """))
        PROVIDER_CLASSES['test.base'] = ProviderBase
        plan(deployment, RequestContext())
        components = [r['component'] for r in deployment['resources'].values()]
        self.assertIn('big_widget', components)
        self.assertIn('small_widget', components)

    def test_component_finding(self):
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    one:
                      component:
                        type: widget
                        interface: foo
                    two:
                      component:
                        id: big_widget
                environment:
                  name: environment
                  providers:
                    base:
                      provides:
                      - widget: foo
                      - widget: bar
                      vendor: test
                      catalog:
                        widget:
                          small_widget:
                            is: widget
                            provides:
                            - widget: foo
                          big_widget:
                            is: widget
                            provides:
                            - widget: bar
                    common:
                      credentials:
                      - password: secret
                        username: tester
            """))
        PROVIDER_CLASSES['test.base'] = ProviderBase
        plan(deployment, RequestContext())
        components = [r['component'] for r in deployment['resources'].values()]
        self.assertIn('big_widget', components)
        self.assertIn('small_widget', components)


class TestDeploymentSettings(unittest.TestCase):

    def test_get_setting(self):
        """Test the get_setting function"""
        deployment = Deployment(yaml_to_dict("""
                environment:
                  providers:
                    base

                blueprint:
                  services:
                    web:
                      component:
                      type: compute
                  options:
                    my_server_type:
                      constrains:
                      - type: compute
                        service: web
                        setting: os
                inputs:
                  blueprint:
                    domain: example.com
                    my_server_type: Ubuntu 11.10  # an option with constraint
                  providers:
                    base:
                      compute:
                        memory: 4 Gb
                  services:
                    web:
                      compute:
                        case-whitespace-test: 512mb
                        gigabyte-test: 8 gigabytes
                        mb-test: 512 Mb
                        memory: 2 Gb
                        number-only-test: 512
            """))
        cases = [{
                'case': "Set in blueprint/inputs",
                'name': "domain",
                'expected': "example.com",
                }, {
                'case': "Set in blueprint/inputs with service/provider scope",
                'name': "os",
                'service': "web",
                'expected': "Ubuntu 11.10",
                }, {
                'case': "Set in blueprint/inputs with no service scope",
                'name': "os",
                'expected': None,
                }, {
                'case': "Set in blueprint/service under provider/resource",
                'name': "memory",
                'service': "web",
                'type': 'compute',
                'expected': "2 Gb",
                }, {
                'case': "Set in blueprint/providers",
                'name': "memory",
                'type': 'compute',
                'expected': "4 Gb",
                'add': """ - FIXME: broken without env providers
                    environment:
                      name: environment
                      providers:
                        base:
                          provides:
                          - compute: foo
                          vendor: test""",
                }
            ]

        PROVIDER_CLASSES['test.base'] = ProviderBase
        for test in cases[:-1]:  # TODO: last case broken without env providers
            value = deployment.get_setting(test['name'],
                    service_name=test.get('service'),
                    provider_key=test.get('provider'),
                    resource_type=test.get('type'))
            self.assertEquals(value, test['expected'], test['case'])

    def test_get_input_provider_option(self):
        deployment = Deployment(yaml_to_dict("""
                environment:
                  providers:
                    base
                blueprint:
                  services:
                    web:
                  options:
                    my_server_type:
                      constrains:
                      - resource_type: compute
                        service: web
                        setting: os
                inputs:
                  blueprint:
                    domain: example.com
                    my_server_type: Ubuntu 11.10
                  providers:
                    base:
                      compute:
                        os: X
                  services:
                    web:
                      compute:
                        case-whitespace-test: 512mb
                        gigabyte-test: 8 gigabytes
                        mb-test: 512 Mb
                        memory: 2 Gb
                        number-only-test: 512
            """))
        fxn = deployment._get_input_provider_option
        self.assertEqual(fxn('os', 'base', resource_type='compute'), 'X')

    def test_get_bad_options(self):
        self.assertRaises(CheckmateValidationException, Deployment,
                yaml_to_dict("""
                environment:
                  providers:
                    base
                blueprint:
                  services:
                    web:
                  options:
                    my_server_type:
                      constrains:
                      - resource_type: compute
                        service: web
                        setting: os
                inputs:
                  blueprint:
                    domain: example.com
                    my_server_type: Ubuntu 11.10
                  providers:
                    base:
                      compute:
                        # Missing!
                  services:
                    web:
                      compute:
                        case-whitespace-test: 512mb
                        gigabyte-test: 8 gigabytes
                        mb-test: 512 Mb
                        memory: 2 Gb
                        number-only-test: 512
            """))

class TestScaleDeployment(unittest.TestCase):
    """ Tests deployment scaling API methods """
    
    def __init__(self, methodName='runTest'):
        self._mox = mox.Mox()
        unittest.TestCase.__init__(self, methodName)
    
    def setUp(self):
        self._mox.StubOutWithMock(checkmate.deployments, "db")
        checkmate.deployments.db.get_deployment("DEP-113a-test").MultipleTimes().AndReturn(Deployment(
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
          'id' : "DEP-113a-test",
          'status':'RUNNING',
          'created':'2012-07-3019:54:34+0000',
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
           # omitted environment/providers for simplicity as this is just for testing the scaling part
        }))
        self._mox.ReplayAll()
        bottle.request.bind({})
        unittest.TestCase.setUp(self)
    
    def tearDown(self):
        self._mox.UnsetStubs()
        unittest.TestCase.tearDown(self)
    
    def test_bad_dep_id(self):
        """ Test that we get the expected exception with a bad deployment id """
        self._mox.UnsetStubs()
        self.assertRaises(HTTPError, scale_deployment, None, None, None, None, tenant_id="1234", amount=1)
        self.assertRaises(HTTPError, scale_deployment,"#1!_", None, None, None, tenant_id="1234", amount=1)
        self.assertRaisesRegexp(HTTPError, "404", scale_deployment,"DEP-113a", None, None, None, tenant_id="1234", amount=1)
    
    def test_missing_service(self):
        """ Test that a bad service throws up """
        try:
            scale_deployment("DEP-113a-test", "notaservice", 'application', 'count', tenant_id="1234", amount=1)
        except HTTPError as err:
            self._mox.VerifyAll()
            self.assertTrue(err.output, "Missing expected error output")
            self.assertRegexpMatches(err.output, "is not defined for deployment")
     
    def test_invalid_vector(self):
        """ Test that specifying a non-existant option fails appropriately """
        try:
            scale_deployment("DEP-113a-test", "testservice", 'application', 'notfound', tenant_id="1234", amount=1)
            self.fail('should not have scaled an invalid setting')
        except HTTPError as err:
            self._mox.VerifyAll()
            self.assertTrue(err.output, "Missing expected error output")
            self.assertRegexpMatches(err.output, "No setting matches")
    
    def test_not_scalable_option(self):
        """ test that you can't scale an option that isn't marked as scalable """
        try:
            scale_deployment("DEP-113a-test", "testservice", 'compute', 'image', tenant_id="1234", amount='linux')
            self.fail('Should not have scaled the os setting')
        except HTTPError as err:
            self._mox.VerifyAll()
            self.assertTrue(err.output, "Missing expected error output")
            self.assertRegexpMatches(err.output, "cannot be scaled for")
           
    def test_invalid_scale(self):
        """ Test that we get an exception if we try to scale more or less than allowed """
        amount = "abc"
        try:
            scale_deployment("DEP-113a-test", "testservice", "application", "count", tenant_id="1234", amount=amount)
            self.fail("Should not have accepted the specified amount %s" % amount)
        except HTTPError as err:
            self._mox.VerifyAll()
            self.assertTrue(err.output, "Missing expected error output")
            self.assertRegexpMatches(err.output, "^Invalid amount \\(%s\\).*" % amount)
        amount = 2
        try:
            scale_deployment("DEP-113a-test", "testservice", "application", "count", tenant_id="1234", amount=amount)
            self.fail("Should not have accepted the specified amount %s" % amount)
        except HTTPError as err:
            self._mox.VerifyAll()
            self.assertTrue(err.output, "Missing expected error output")
            self.assertRegexpMatches(err.output, "between 1 and 4")
        # test non-scalar scaling
        amount = "not_an_amount"
        try:
            scale_deployment("DEP-113a-test", "testservice", "compute", "size", tenant_id="1234", amount=amount)
            self.fail("Should not have accepted the specified amount %s" % amount)
        except HTTPError as err:
            self._mox.VerifyAll()
            self.assertTrue(err.output, "Missing expected error output")
            self.assertRegexpMatches(err.output, "Must be one of")
    
    def test_happy_path(self):
        """ Test that we get a valid looking deployment back if everything looks good """
        ret = json.loads(scale_deployment("DEP-113a-test", "testservice", "application", "count", tenant_id="1234", amount=1))
        # FIXME: this next test should fail once the actual implementation is sorted
        self.assertIn("message", ret, "Did not find expected message in response.")
        self.assertEqual(4, ret['inputs']['services']['testservice']['application']['count'], '"count" setting not updated')
        ret = json.loads(scale_deployment("DEP-113a-test", "testservice", "compute", "size", tenant_id="1234", amount="bigger"))
        # FIXME: this next test should fail once the actual implementation is sorted
        self.assertIn("message", ret, "Did not find expected message in response.")
        self.assertEqual('4', ret['inputs']['services']['testservice']['compute']['size'], '"os" setting not updated')

if __name__ == '__main__':
    unittest.main()
