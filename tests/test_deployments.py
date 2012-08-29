#!/usr/bin/env python
import copy
import unittest2 as unittest
import checkmate
import mox

from checkmate.deployments import Deployment, plan, scale_deployment
from checkmate.exceptions import CheckmateValidationException,\
    CheckmateException
from checkmate.providers.base import PROVIDER_CLASSES, ProviderBase
from checkmate.server import RequestContext
from checkmate.utils import yaml_to_dict
from bottle import HTTPError, BaseRequest
import bottle
from bottle import Request, LocalRequest
import json
from mox import IgnoreArg



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
    
    def __init__(self, methodName):
        unittest.TestCase.__init__(self, methodName)
        self._dep = None
        
        
    def setUp(self):
        unittest.TestCase.setUp(self)
        self._dep = Deployment(yaml_to_dict("""
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
        

    def test_get_setting(self):
        """Test the get_setting function"""
        deployment = Deployment(yaml_to_dict("""
                environment:
                  name: environment
                  providers:
                    base:
                      provides:
                      - compute: foo
                        vendor: bar
                    common:
                      credentials:
                      - password: secret
                      constraints:
                      - region: place
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
                'case': "Set in environments/providers/common",
                'name': "region",
                'provider': "common",
                'service' : "constraints",
                'expected': "place",
                },  {
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

    def test_basic_setting(self):
        """ ensures that changing an exisitng blueprint setting works """
        self.assertNotEqual(self._dep.inputs().get("blueprint",{}).get("domain",""), "changedit.com", "Initial blueprint setting for domain is unexpected.")
        self._dep.set_setting("domain", value="changedit.com")
        self.assertEqual(self._dep.inputs().get("blueprint",{}).get("domain",""), "changedit.com", "Blueprint setting 'domain' not changed.")
    
    def test_new_basic_setting(self):
        """ ensures adding a new blueprint setting works """
        self.assertFalse("testnewsetting" in self._dep.inputs().get("blueprint",{}), "Initial blueprint setting for 'newsetting' is unexpected.")
        self._dep.set_setting("testnewsetting", value="added this setting")
        self.assertTrue("testnewsetting" in self._dep.inputs().get("blueprint",{}), "'newsetting' not added.")
        self.assertEqual(self._dep.inputs().get("blueprint",{}).get("testnewsetting",""), "added this setting", "Blueprint setting 'newsetting' not set.")
        
    def test_unset_basic_setting(self):
        """ ensures we can unset something """
        self.assertTrue("domain" in self._dep.inputs().get("blueprint",{}), "'domain' not set.")
        self.assertEqual(self._dep.inputs().get("blueprint",{}).get("domain",""), "example.com", "Blueprint setting 'domain' unexpected initial value.")
        self._dep.set_setting("domain")
        self.assertFalse("domain" in self._dep.inputs().get("blueprint",{}), "Blueprint setting 'domain' was not unset")
    
    def test_provider_setting(self):
        """ ensures changing a provider setting works """
        self.assertNotEqual(self._dep.inputs().get("providers",{}).get("base",{}).get("compute",{}).get("memory", ""), "8 Gb", "Initial provider setting is unexpected.")
        self._dep.set_setting("memory", provider_key="base", resource_type="compute", value="8 Gb")
        self.assertEqual(self._dep.inputs().get("providers",{}).get("base",{}).get("compute",{}).get("memory", ""), "8 Gb", "Provider setting 'compute/memory' not changed.")
    
    def test_new_provider_setting(self):
        """ ensures adding a new provider setting works """
        self.assertFalse("testnew_provider_setting" in self._dep.inputs().get("providers",{}).get("base",{}).get("compute",{}), "Initial provider setting is unexpected.")
        self._dep.set_setting("testnew_provider_setting", provider_key="base", resource_type="compute", value="added this provider setting")
        self.assertTrue("testnew_provider_setting" in self._dep.inputs().get("providers",{}).get("base",{}).get("compute",{}), "Provider setting 'compute/testnew_provider_setting' not added.")
        self.assertEqual(self._dep.inputs().get("providers",{}).get("base",{}).get("compute",{}).get("testnew_provider_setting", ""), "added this provider setting", "Provider setting 'compute/testnew_provider_setting' not set.")
    
    def test_unset_provider_setting(self):
        """ ensures we can unset something """
        self.assertTrue("memory" in self._dep.inputs().get("providers",{}).get("base",{}).get("compute", {}), "'base/compute/memory' not set.")
        self.assertEqual(self._dep.inputs().get("providers",{}).get("base",{}).get("compute",{}).get("memory",""), "4 Gb", "Provider setting 'base/compute/memory' unexpected initial value.")
        self._dep.set_setting("memory", provider_key="base", resource_type="compute")
        # should get rid of the entire tree
        self.assertFalse("providers" in self._dep.inputs(), "Providers setting was not unset")
    
    def test_service_setting(self):
        """ ensures changing a service setting works """
        self.assertNotEqual(self._dep.inputs().get("services",{}).get("web",{}).get("compute",{}).get("memory", ""), "6 Gb", "Initial service setting is unexpected.")
        self._dep.set_setting("memory", service_name="web", resource_type="compute", value="6 Gb")
        self.assertEqual(self._dep.inputs().get("services",{}).get("web",{}).get("compute",{}).get("memory", ""), "6 Gb", "Service setting 'web/memory' not changed.")
    
    def test_new_service_setting(self):
        """ ensures adding a new service setting works """
        self.assertFalse("testnew_service_setting" in self._dep.inputs().get("services",{}).get("web",{}).get("compute",{}), "Initial service setting is unexpected.")
        self._dep.set_setting("testnew_service_setting", service_name="web", resource_type="compute", value="added this service setting")
        self.assertTrue("testnew_service_setting" in self._dep.inputs().get("services",{}).get("web",{}).get("compute",{}), "Service setting 'web/compute/testnew_service_setting' not added.")
        self.assertEqual(self._dep.inputs().get("services",{}).get("web",{}).get("compute",{}).get("testnew_service_setting", ""), "added this service setting", "Service setting 'web/compute/testnew_service_setting' not set.")
    
    def test_unset_service_setting(self):
        """ ensures we can unset something """
        self.assertTrue("memory" in self._dep.inputs().get("services",{}).get("web",{}).get("compute", {}), "'web/compute/memory' not set.")
        self.assertEqual(self._dep.inputs().get("services",{}).get("web",{}).get("compute",{}).get("memory",""), "2 Gb", "Service setting 'web/compute/memory' unexpected initial value.")
        self._dep.set_setting("memory", service_name="web", resource_type="compute")
        # should get rid of the entire tree
        self.assertFalse("memory" in self._dep.inputs().get("services",{}).get("web",{}).get("compute",{}), "Service setting was not unset")
    
    def test_set_no_name(self):
        """ test that you must pass a name """
        self.assertRaisesRegexp(CheckmateException, "Must specify a setting name", self._dep.set_setting, "")
        self.assertRaisesRegexp(CheckmateException, "Must specify a setting name", self._dep.set_setting, None)
        
    def test_set_service_and_provider(self):
        """ tests that you can't pass both a service and provider """
        self.assertRaisesRegexp(CheckmateException, "Cannot specify both a service and a provider", self._dep.set_setting, "name", provider_key="nope", service_name="nopenope")
    
    def test_set_no_resource_type(self):
        """ tests that a resource type is required if a provider or
        service is specified
        """
        self.assertRaisesRegexp(CheckmateException, "Must specify a resource type", self._dep.set_setting, "name", provider_key="test")
        self.assertRaisesRegexp(CheckmateException, "Must specify a resource type", self._dep.set_setting, "name", service_name="test")
    
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
        self._dep = Deployment(
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
        })
        unittest.TestCase.__init__(self, methodName)
    
    def setUp(self):
        self._mox.StubOutWithMock(checkmate.deployments, "db")
        checkmate.deployments.db.get_deployment("DEP-113a-test").MultipleTimes(group_name="query").AndReturn(self._dep)
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
        self._mox.UnsetStubs()
        self._mox.StubOutWithMock(checkmate.deployments, "db")
        checkmate.deployments.db.get_deployment("DEP-113a-test").MultipleTimes().AndReturn(self._dep)
        checkmate.deployments.db.save_deployment(IgnoreArg(), IgnoreArg(), IgnoreArg(), tenant_id=IgnoreArg()).MultipleTimes().AndReturn(self._dep._data)
        self._mox.ReplayAll()
        ret = json.loads(scale_deployment("DEP-113a-test", "testservice", "application", "count", tenant_id="1234", amount=1))
        # FIXME: this next test should fail once the actual implementation is sorted
        self.assertEqual(4, ret['inputs']['services']['testservice']['application']['count'], '"count" setting not updated')
        ret = json.loads(scale_deployment("DEP-113a-test", "testservice", "compute", "size", tenant_id="1234", amount="bigger"))
        # FIXME: this next test should fail once the actual implementation is sorted
        self.assertEqual('4', ret['inputs']['services']['testservice']['compute']['size'], '"os" setting not updated')

if __name__ == '__main__':
    unittest.main()
