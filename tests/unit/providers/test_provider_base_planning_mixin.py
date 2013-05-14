import logging
from checkmate.deployment import Deployment
from checkmate.middleware import RequestContext
import mox
import unittest2 as unittest
from checkmate.providers.provider_base_planning_mixin \
    import ProviderBasePlanningMixIn

LOG = logging.getLogger(__name__)


class TestProviderBasePlanningMixIn(unittest.TestCase):
    def setUp(self):
        self.req_context = RequestContext()
        self.deployment_mocker = mox.Mox()
        self.deployment = self.deployment_mocker.CreateMock(Deployment)

    def test_template(self):
        provider_key = 'test_key'
        resource_type = 'test_type'
        service_name = 'testService'
        self.deployment.get_setting('domain', provider_key=provider_key,
                                        resource_type=resource_type,
                                        service_name=service_name,
                                        default='checkmate.local')\
            .AndReturn('test.checkmate')
        self.deployment._constrained_to_one(service_name).AndReturn(True)
        self.deployment_mocker.ReplayAll()
        templates = ProviderBasePlanningMixIn().generate_template(
            self.deployment,
            resource_type,
            service_name,
            self.req_context, 1, provider_key, None)
        template = templates[0]
        self.assertEqual("test_type", template.get("type", "NONE"),
                         "Type not set")
        self.assertEqual("test_key",
                         template.get("provider", "NONE"),
                         "Provider not set")
        self.assertIn("instance", template, "No instance in template")
        self.assertEqual("testService.test.checkmate",
                         template.get("dns-name", "NONE"),
                         "dns-name not set")

    def test_get_resource_name_when_service_is_constrained_to_one(self):
        service = 'testService'
        self.deployment._constrained_to_one(service).AndReturn(True)
        self.deployment_mocker.ReplayAll()

        resource_name = ProviderBasePlanningMixIn()\
            .get_resource_name(self.deployment, "testDomain", 1, service, None)
        self.assertEqual("testService.testDomain", resource_name)

    def test_get_resource_name_when_service_is_not_constrained_to_one(self):
        deployment = self.deployment_mocker.CreateMock(Deployment)
        service = 'testService'
        deployment._constrained_to_one(service).AndReturn(False)
        self.deployment_mocker.ReplayAll()

        resource_name = ProviderBasePlanningMixIn()\
            .get_resource_name(deployment, "testDomain", 1, service, None)
        self.assertEqual("testService01.testDomain", resource_name)

    def test_get_resource_name_when_service_is_None(self):
        resource_type = "user"
        resource_name = ProviderBasePlanningMixIn()\
            .get_resource_name(None, "testDomain", 1, None, resource_type)
        self.assertEqual("shared%s.testDomain" % resource_type, resource_name)

    def tearDown(self):
        self.deployment_mocker.VerifyAll()

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