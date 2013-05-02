# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method '''

import unittest2 as unittest

from checkmate.providers import base
from checkmate.providers.base import ProviderBase
from checkmate.deployments import Deployment, plan
from checkmate.middleware import RequestContext
from checkmate.plan import Plan
from checkmate.exceptions import (
    CheckmateException,
    CheckmateValidationException,
)
from checkmate import utils


class TestDeploymentPlanning(unittest.TestCase):
    """Tests the Plan() class and its deployment planning logic"""
    def test_find_components_positive(self):
        """Test the Plan() class can find components"""
        deployment = Deployment(utils.yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    by_id:
                      component:
                        id: widget_with_id
                    by_interface:
                      component:
                        interface: foo
                    by_type:
                      component:
                        resource_type: gadget
                    by_type_and_interface:
                      component:
                        interface: bar
                        resource_type: gadget
                  meta-data:
                    schema-version: v0.7
                environment:
                  name: environment
                  providers:
                    base:
                      vendor: test
                      catalog:
                        widget:
                          widget_with_id:
                            id: widget_with_id
                            is: widget
                          foo_widget:
                            is: widget
                            provides:
                            - widget: foo
                    gbase:
                      vendor: test
                      catalog:
                        gadget:
                          bar_gadget:
                            is: gadget
                            provides:
                            - gadget: bar
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase
        base.PROVIDER_CLASSES['test.gbase'] = ProviderBase

        planner = Plan(deployment)
        planner.plan(RequestContext())

        services = planner['services']
        self.assertIn('by_id', services)
        self.assertIn('by_interface', services)
        self.assertIn('by_type', services)
        self.assertIn('by_type_and_interface', services)
        self.assertEqual(len(services), 4)

        component = services['by_id']['component']
        self.assertEqual(component['id'], 'widget_with_id')
        self.assertEqual(component['provider'], 'checkmate.base')
        self.assertEqual(component['provider-key'], 'base')

        component = services['by_interface']['component']
        self.assertEqual(component['id'], 'foo_widget')
        self.assertEqual(component['provider'], 'checkmate.base')
        self.assertEqual(component['provider-key'], 'base')

        component = services['by_type']['component']
        self.assertEqual(component['id'], 'bar_gadget')
        self.assertEqual(component['provider'], 'checkmate.base')
        self.assertEqual(component['provider-key'], 'gbase')

        component = services['by_type_and_interface']['component']
        self.assertEqual(component['id'], 'bar_gadget')
        self.assertEqual(component['provider'], 'checkmate.base')
        self.assertEqual(component['provider-key'], 'gbase')

    def test_find_components_not_found(self):
        """Test the Plan() class fails missing components"""
        deployment = Deployment(utils.yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    by_id:
                      component:
                        id: widget_with_id  # id does not exist in catalog
                environment:
                  name: environment
                  providers:
                    base:
                      vendor: test
                      catalog:
                        widget:
                          foo_widget:
                            is: widget
                            provides:
                            - widget: foo
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase

        planner = Plan(deployment)
        self.assertRaises(CheckmateException, planner.plan, RequestContext())

    def test_find_components_mismatch(self):
        """Test the Plan() class skips mismatched components"""
        deployment = Deployment(utils.yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    by_id:
                      component:
                        id: widget_with_id
                        resource_type: gadget  # only widget in catalog
                environment:
                  name: environment
                  providers:
                    base:
                      vendor: test
                      catalog:
                        widget:
                          widget_with_id:
                            id: widget_with_id
                            is: widget
                            provides:
                            - widget: foo
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase

        planner = Plan(deployment)
        self.assertRaises(CheckmateException, planner.plan, RequestContext())

    def test_resolve_relations(self):
        """Test the Plan() class can parse relations"""
        deployment = Deployment(utils.yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    main:
                      component:
                        id: main_widget
                      relations:
                        explicit: foo
                    explicit:
                      component:
                        id: foo_widget
                environment:
                  name: environment
                  providers:
                    base:
                      vendor: test
                      catalog:
                        widget:
                          main_widget:
                            is: widget
                            requires:
                            - widget: foo
                          foo_widget:
                            is: widget
                            provides:
                            - widget: foo
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase

        planner = Plan(deployment)
        planner.plan(RequestContext())
        services = planner['services']
        component = services['main']['component']
        widget_foo = component['requires']['widget:foo']
        expected = {
            'interface': 'foo',
            'resource_type': 'widget',
            'satisfied-by': {
                'name': 'main-explicit',
                'relation-key': 'main-explicit',
                'service': 'explicit',
                'component': 'foo_widget',
                'provides-key': 'widget:foo',
            }
        }
        self.assertDictEqual(widget_foo, expected)

    #FIXME: re-enable this when done with v0.2
    @unittest.skip("Not compatible with v0.2 relations")
    def test_resolve_relations_negative(self):
        """Test the Plan() class detects unused/duplicate relations"""
        deployment = Deployment(utils.yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    main:
                      component:
                        id: main_widget
                      relations:
                        explicit: foo
                        "duplicate-provides":
                          service: named
                          interface: foo
                    explicit:
                      component:
                        id: foo_widget
                    named:
                      component:
                        id: foo_widget
                environment:
                  name: environment
                  providers:
                    base:
                      vendor: test
                      catalog:
                        widget:
                          main_widget:
                            is: widget
                            requires:
                            - widget: foo
                          foo_widget:
                            is: widget
                            provides:
                            - widget: foo
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase
        planner = Plan(deployment)
        self.assertRaises(CheckmateValidationException, planner.plan,
                          RequestContext())

    def test_resolve_relations_multiple(self):
        """Test that all relations are generated"""
        deployment = Deployment(utils.yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    balanced:
                      component:
                        id: balancer_widget
                      relations:
                        master: foo
                        slave: foo
                    master:
                      component:
                        resource_type: widget
                        interface: foo
                    slave:
                      component:
                        resource_type: widget
                        interface: foo
                        constraints:
                        - count: 2
                      relations:
                        "allyourbase":
                          service: back
                          interface: bar
                    back:
                      component:
                        type: widget
                        interface: bar
                environment:
                  name: environment
                  providers:
                    base:
                      vendor: test
                      catalog:
                        widget:
                          balancer_widget:
                            is: widget
                            requires:
                            - widget: foo
                          web_widget:
                            is: widget
                            requires:
                            - widget: bar
                            - host: windows
                            provides:
                            - widget: foo
                          data_widget:
                            is: widget
                            provides:
                            - widget: bar
                            requires:
                            - host: windows
                          compute_widget:
                            is: compute
                            provides:
                            - compute: windows
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase

        planner = Plan(deployment)
        planner.plan(RequestContext())

        resources = {key: [] for key in planner['services'].keys()}
        for key, resource in planner.resources.iteritems():
            if key != 'connections':
                resources[resource['service']].append(resource)

        expect = "Expecting one 'back' resource"
        self.assertEqual(len(resources['back']), 2, msg=expect)
        back = resources['back'][0]
        back_host = resources['back'][1]
        if back['type'] != 'widget':
            back, back_host = back_host, back

        expect = "Expecting two 'slave' resources and two hosts (four total)"
        self.assertEqual(len(resources['slave']), 4, msg=expect)
        slave1host = resources['slave'][0]
        slave1 = resources['slave'][1]
        slave2host = resources['slave'][2]
        slave2 = resources['slave'][3]
        expect = "Hosts dedicated"
        self.assertEqual(slave1host['hosts'], [slave1['index']], msg=expect)
        self.assertEqual(slave1['hosted_on'], slave1host['index'], msg=expect)
        self.assertEqual(slave2host['hosts'], [slave2['index']], msg=expect)
        self.assertEqual(slave2['hosted_on'], slave2host['index'], msg=expect)

        expect = "Expecting connections from all 'front' resources to 'back'"
        self.assertIn('relations', back)
        self.assertIn('allyourbase-%s' % slave1['index'], back['relations'],
                      msg=expect)
        self.assertIn('allyourbase-%s' % slave2['index'], back['relations'],
                      msg=expect)

    def test_resolve_requirements(self):
        """Test the Plan() class can resolve all requirements"""
        deployment = Deployment(utils.yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    main:
                      component:
                        id: main_widget
                      relations:
                        explicit: foo
                    explicit:
                      component:
                        id: foo_widget
                environment:
                  name: environment
                  providers:
                    base:
                      vendor: test
                      catalog:
                        widget:
                          main_widget:
                            is: widget
                            requires:
                            - widget: foo
                            - host: bar
                          foo_widget:
                            is: widget
                            provides:
                            - widget: foo
                            requires:
                            - host: linux
                          bar_widget:
                            is: widget
                            provides:
                            - widget: bar
                            requires:
                            - gadget: mysql
                          bar_gadget:
                            is: gadget
                            provides:
                            - gadget: mysql
                          linux_instance:
                            is: compute
                            provides:
                            - compute: linux
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase

        planner = Plan(deployment)
        planner.plan(RequestContext())
        services = planner['services']

        component = services['main']['component']
        widget_foo = component['requires']['widget:foo']
        expected = {
            'interface': 'foo',
            'resource_type': 'widget',
            'satisfied-by': {
                'name': 'main-explicit',
                'relation-key': 'main-explicit',
                'service': 'explicit',
                'component': 'foo_widget',
                'provides-key': 'widget:foo',
            }
        }
        self.assertDictEqual(widget_foo, expected)

        host_bar = component['requires']['host:bar']
        expected = {
            'interface': 'bar',
            'relation': 'host',
            'satisfied-by': {
                'name': 'host:bar',
                'service': 'main',
                'component': 'bar_widget',
                'provides-key': 'widget:bar',
            }
        }
        self.assertDictEqual(host_bar, expected)

        self.assertIn('gadget:mysql', services['main']['extra-components'])
        recursive = services['main']['extra-components']['host:bar']
        expected = {
            'interface': 'mysql',
            'resource_type': 'gadget',
            'satisfied-by': {
                'name': 'gadget:mysql',
                'service': 'main',
                'component': 'bar_gadget',
                'provides-key': 'gadget:mysql',
            }
        }
        self.assertDictEqual(recursive['requires']['gadget:mysql'], expected)

        host = planner.resources['4']
        self.assertNotIn('relations', host, msg="Host is not supposed to have "
                                                "any relations but host")

    def test_relation_names(self):
        """Test the Plan() class handles relation naming correctly"""
        deployment = Deployment(utils.yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    front:
                      component:
                        id: start_widget
                      relations:
                        middle: foo  # shorthand
                    middle:
                      component:
                        id: link_widget
                      relations:
                        "john":  # long form
                          service: back
                          interface: bar
                    back:
                      component:
                        id: big_widget  # implicit requirement for gadget:mysql
                environment:
                  name: environment
                  providers:
                    base:
                      vendor: test
                      catalog:
                        widget:
                          start_widget:
                            is: widget
                            requires:
                            - widget: foo
                          link_widget:
                            is: widget
                            provides:
                            - widget: foo
                            requires:
                            - widget: bar
                          big_widget:
                            is: widget
                            provides:
                            - widget: bar
                            requires:
                            - gadget: mysql
                          end_gadget:
                            is: gadget
                            provides:
                            - gadget: mysql
                            requires:
                            - host: linux
                          another_end:
                            is: compute
                            provides:
                            - compute: linux
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase

        plan(deployment, RequestContext())
        resources = deployment['resources']

        expected = utils.yaml_to_dict("""
                  front-middle:       # easy to see this is service-to-service
                    interface: foo
                  john:               # this is explicitely named
                    interface: bar
                                      # 'host' does not exist
            """)
        self.assertDictEqual(resources['connections'], expected)

    def test_resource_name(self):
        """Test the Plan() class handles resource naming correctly"""
        deployment = Deployment(utils.yaml_to_dict("""
                id: test
                environment:
                  providers:
                    base:
                      vendor: test
                      catalog:
                        widget:
                          bar: {}
                blueprint:
                  services:
                    web:
                      component:
                        id: bar
            """))
        base.PROVIDER_CLASSES['test.base'] = ProviderBase
        plan(deployment, RequestContext())
        assigned_name = deployment['resources']['0']['dns-name']
        expected_name = "web01.checkmate.local"
        self.assertEqual(assigned_name, expected_name)

    def test_constrained_resource_name(self):
        """Test the Plan() class handles resource naming correctly"""
        deployment = Deployment(utils.yaml_to_dict("""
                id: test
                environment:
                  providers:
                    base:
                      vendor: test
                      catalog:
                        widget:
                          bar: {}
                blueprint:
                  services:
                    web:
                      component:
                        id: bar
                      constraints:
                        - count: 1
                inputs: {}
            """))
        base.PROVIDER_CLASSES['test.base'] = ProviderBase
        plan(deployment, RequestContext())
        assigned_name = deployment['resources']['0']['dns-name']
        expected_name = "web.checkmate.local"
        self.assertEqual(assigned_name, expected_name)

    def test_evaluate_defaults(self):
        default_plan = Plan(Deployment(utils.yaml_to_dict("""
                id: test
                blueprint:
                  options:
                    defpass:
                      default: =generate_password()
                    defuuid:
                      default: =generate_uuid()
                    static:
                      default: 1
                    none:
                      type: string
                environment:
                  providers:
            """)))
        default_plan.evaluate_defaults()
        options = default_plan.deployment['blueprint']['options']
        defpass = options['defpass']['default']
        defuuid = options['defuuid']['default']
        self.assertNotEqual(defpass, "=generate_password()")
        self.assertNotEqual(defuuid, "=generate_uuid()")
        default_plan.evaluate_defaults()  # test idempotency
        self.assertEqual(defpass, options['defpass']['default'])
        self.assertEqual(defuuid, options['defuuid']['default'])


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
