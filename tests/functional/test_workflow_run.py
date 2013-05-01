# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import copy
import json
import logging
import os
import unittest2 as unittest
import yaml

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from string import Template
from checkmate.deployments import Deployment
from checkmate.test import StubbedWorkflowBase, ENV_VARS
from checkmate.utils import yaml_to_dict
from checkmate.providers import base
from checkmate.providers.base import ProviderBase
from checkmate.utils import resolve_yaml_external_refs


class TestWorkflowStubbing(StubbedWorkflowBase):
    """Test workflow stubbing using mox"""
    def test_workflow_run(self):
        self.deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services: {}
                environment:
                  name: environment
                  providers: {}
                """))

        workflow = self._get_stubbed_out_workflow()

        self.mox.ReplayAll()

        workflow.complete_all()
        self.assertTrue(workflow.is_completed())
        self.assertNotIn('resources', self.deployment)


class TestWorkflowLogic(StubbedWorkflowBase):
    """Test Basic Workflow code"""
    def test_workflow_resource_generation(self):
        self.deployment = Deployment(yaml_to_dict("""
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
        base.PROVIDER_CLASSES['test.base'] = ProviderBase

        workflow = self._get_stubbed_out_workflow()

        self.mox.ReplayAll()

        workflow.complete_all()
        self.assertTrue(workflow.is_completed())
        self.assertEqual(len(workflow.get_tasks()), 3)


class TestWorkflow(StubbedWorkflowBase):
    """Test Workflow Execution"""

    def setUp(self):
        StubbedWorkflowBase.setUp(self)

    def test_workflow_completion(self):
        """Verify workflow sequence and data flow"""

        self.deployment = Deployment(yaml_to_dict("""
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
        base.PROVIDER_CLASSES['test.base'] = ProviderBase
        self.workflow = self._get_stubbed_out_workflow()

        self.mox.ReplayAll()

        self.workflow.complete_all()
        self.assertTrue(self.workflow.is_completed())

        LOG.debug("RESOURCES:")
        LOG.debug(json.dumps(self.deployment['resources'], indent=2))
        LOG.debug("\nOUTCOME:")
        LOG.debug(json.dumps(self.outcome, indent=2))


class TestWordpressWorkflow(StubbedWorkflowBase):
    """Test WordPress Workflow inputs (modifies app.yaml)"""

    @classmethod
    def setUpClass(cls):
        # Load app.yaml, substitute variables
        path = os.path.join(os.path.dirname(__file__), '..', 'examples',
                            'app.yaml')
        with file(path) as f:
            source = f.read().decode('utf-8')

        t = Template(source)
        combined = copy.copy(ENV_VARS)
        combined.update(os.environ)
        parsed = t.safe_substitute(**combined)
        app = yaml.safe_load(yaml.emit(resolve_yaml_external_refs(parsed),
                                       Dumper=yaml.SafeDumper))
        app['id'] = 'DEP-ID-1000'

        # WordPress Settings
        inputs = yaml_to_dict("""
            client_public_key_ssh: %s
            environment_private_key: |
            -----BEGIN RSA PRIVATE KEY-----
            MIIEpAIBAAKCAQEAvQYtPZCP+5SVD68nf9OzEEE7itZlfynbf/XRQ6YggOa0t1U5
            XRqdHPnmG7nYtxdMQLZkMYJtyML8u56p11DrpQCF9p9VISrnjSS4CmO2Y6vLbd2H
            yntKeV57repsAnhqkE788rWQ5bm15bYyYLa52qhpYxy3R7O/Nif3B1wQzq0+KYbD
            MqoHs7dOGErKXxRcqO1f1WZe6gBfat2qDY/XUJe+VQXNSGl7e19KSr9FZXMTQBOs
            sGvleL0mDy0Gn9NKp9V3haKmAMPW0ZAMA14TqwBfHaELPuRLrCDRt6YtDLGg4V+w
            vgZdGkzwoEAAAuKheu+5TwEBrD9wO4fE/C8sBwIDAQABAoIBAGzHaDOcxO9f82Ri
            RRXv64V4NN7SQPisSvBZs4L90Ii9u9QhjHCDB1WMjpr4GbpMAwreq8w+JhW5+J20
            UkNiAyoiofVqfiAnQ7fbILqB5Y14aQqhySqCRzqPYBeW52+IgrLncfPu/yLk+8Pl
            VRqJLW2jK3rpJKRz0Z9F4ohuuBFnbjsGtjknivH+Xd6KR9022mzNiBinjD/R8R+K
            GW75buDzquvuaQ12mHub4uQ59hhyp2a/jrwy6ez0lbXu3zqIyzPzhHk95WLMmrDv
            AeyzqkjcbuJ1VBv8ko8enp56m9CQvoPnmYHW8xI53I4yCzp6yymd9/mgFj6CoSyv
            Z/NUIJkCgYEA2A9ibxjvNVF/s6lKhb8WGRhSlQZoZT3u360ok8JzPDWwEOyEEUy2
            OFJDJ8gtJ6PelQD2b9xaz+dGWEfZU2CGL68KtiRmO5uDD5BmJ02UmjfBUl/7uipl
            BhtZLDexj1vORZQMrhSrxt7n1VfEgpX42n0WR/EU4aoWSX1CAIG2AksCgYEA3/de
            YCuHYjEscDbkee0CSqBfdg/u01+HRE+fQ8AesNLC1ZZv7h5OfCfrZvM925Kk+0tm
            ex8IdMfnuGaF3E25mkAshDeQQO5kj14KcJ8GD9z3qG6iiWOcTJtFw8CNkbPe9SfT
            9FmYPZbvXGeIQvj6b9dEVRJOcI+4WsoiMgOeh7UCgYEAqhmSmXy79vIu47dIYHvM
            Xf10JrdgwTQ9OAQPiiTwrFpoPyq13xjR7Q12qX9DbY3p0s1rNy34oO2nyCDozGeV
            vTzF5hhKFGueh0Zb5l2BvNhgbwX6HNr7pg8p6VH/jKnuf4DLatIDWxJq2t+6akTA
            IuOQAxueIPvTiBABQnzcWnkCgYAtWHNGO2n0yon5ylNmEEOXgnLxf3ZWW5ASl6Bi
            YkKUgIesIQJWjtJLNvXlaThL/ZvjuTdtlDHtGxBieHd/zEjY30dkGa/eRaYclOi+
            NqROj+mgs427DWz24bU1VgYTyvxIXKEAZyd4yNd7uQaQsMJb5JTUOJmjFqY305cq
            0yrExQKBgQCB2Be1RFBkLa+7VGpK+kT7OVHhmMAMjr9apL4XI6WYQzeS+JN6elG3
            hEN1X4K28pVFgiQKqoUZhTjo9MGJsiA8TJ8QX4fLqfyhzitV98zTvPar4i/3bATc
            /lQOh9JeTc7pCXHX9A2sVT0A7XNR2riT+zoof5edWIBK0UFSA8u0Vw==
            -----END RSA PRIVATE KEY-----
            blueprint:
              "prefix": TEST-BLOG
              "domain": testing.local
              "path": '/test_blog'
              "username": tester
              "password": test_password
              "ssl": true
              "ssl_certificate": SSLCERT
              "ssl_private_key": SSLKEY
              "region": 'ORD'
              "high-availability": true
              "requests-per-second": 60
            services:
              "backend":
                'database':
                  'memory': 1024 Mb
              "web":
                'compute':
                  'memory': 2048 Mb
                'application':
                  'count': 2
            providers:
              'legacy':
                'compute':
                  'os': Ubuntu 12.04
                  """ % ENV_VARS['CHECKMATE_CLIENT_PUBLIC_KEY'])
        app['inputs'] = inputs
        cls.deployment = Deployment(app)

    def setUp(self):
        StubbedWorkflowBase.setUp(self)
        # Parse app.yaml as a deployment
        self.deployment = TestWordpressWorkflow.deployment
        self.workflow = self._get_stubbed_out_workflow()

    #def test_workflow_completion(self):
    #    'Verify workflow sequence and data flow'
    #
    #    self.mox.ReplayAll()
    #
    #    def recursive_tree(task, indent):
    #        print ' ' * indent, task.id, "-", task.name
    #        for child in task.outputs:
    #            recursive_tree(child, indent + 1)
    #
    #    def pp(workflow):
    #        print workflow.spec.name
    #        recursive_tree(workflow.spec.start, 1)
    #
    #        for id, task in workflow.spec.task_specs.iteritems():
    #            if task.inputs:
    #                print task.id, "-", id
    #            else:
    #                print task.id, "-", id, "    >>>>  DICONNECTED!"
    #
    #    pp(self.workflow)
    #
    #    self.workflow.complete_all()
    #    self.assertTrue(self.workflow.is_completed(), "Workflow did not "
    #                    "complete")
    #
    #    LOG.debug("RESOURCES:")
    #    LOG.debug(json.dumps(self.deployment['resources'], indent=2))
    #    LOG.debug("\nOUTCOME:")
    #    LOG.debug(json.dumps(self.outcome, indent=2))
    #
    #   self.assertIn('data_bags', self.outcome)
    #    self.assertIn('DEP-ID-1000', self.outcome['data_bags'])
    #
    #    databag = self.outcome['data_bags']['DEP-ID-1000']
    #    self.assertIn('webapp_wordpress_TEST-BLOG', databag)
    #
    #    item = databag['webapp_wordpress_TEST-BLOG']
    #    self.assertIn('wordpress', item)
    #    self.assertIn('lsyncd', item)
    #    self.assertIn('mysql', item)
    #    self.assertEqual(len(self.deployment['blueprint']['services']['web']\
    #                         ['instances']), 4)  # 2 hosts + 2 apps
    #    count = 0
    #    for resource in self.deployment['resources'].values():
    #        if resource.get('provider') == 'legacy':
    #            self.assertEquals(resource['image'], "125")
    #            count += 1
    #    for key in self.deployment['blueprint']['services']['web']\
    #            ['instances']:
    #        resource = self.deployment['resources'][key]
    #        if resource['provider'] == 'legacy':
    #            self.assertEquals(resource['flavor'], "4")  # 2Gb for web
    #    for key in self.deployment['blueprint']['services']['master']\
    #            ['instances']:
    #        resource = self.deployment['resources'][key]
    #        if resource['provider'] == 'legacy':
    #            self.assertEquals(resource['flavor'], "2")  # 1Gb for master
    #    self.assertEqual(count, 3)  # 1 master, 2 webs


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    sys.path.insert(1, os.path.join(sys.path[0], '../..'))
    from tests.utils import run_with_params
    run_with_params(sys.argv[:])
