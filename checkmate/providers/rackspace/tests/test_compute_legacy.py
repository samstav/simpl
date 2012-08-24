!#/usr/bin/env python
import logging
import unittest2 as unittest

from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate.providers.rackspace import compute_legacy

from checkmate.deployments import Deployment, resource_postback
from checkmate.providers.base import PROVIDER_CLASSES
from checkmate.test import StubbedWorkflowBase, TestProvider
from checkmate.utils import yaml_to_dict

class TestLegacyCompute(unittest.TestCase):
    """ Test Legacy Compute Provider """

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_provider(self):
        provider = compute_legacy.provider({})
        self.assertEqual(provider.key, 'rackspace.compute_legacy'

    def test_create_server(self):
        #Mock server
        server = self.mox.CreateMockAnything()
        server.id = 'fake_server_id'
        server.status = 'BUILD'
        server.ip = '1.2.3.4'
        server.priave_ip = '5.6.7.8'
        server.adminPass = 'password'

        #Create openstack.compute mock
        openstack_api_mock = self.mox.CreateMockAnything()
        openstack_api_mock.servers.create(image=1, flavor=1, \
            name='fake_server', files=None).AndReturn(server)

        expected = {
                'id': server.id
                'ip': server.ip,
                'password': server.adminPass,
                'private_ip': server.private_ip
                }

        context = dict(deployment='DEP', resource='1')
        resource_postback.delay(context['deployment'], expected).AndReturn(True)

        self.mox.ReplayAll()
        results = compute_legacy.create_server()    
