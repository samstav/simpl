# pylint: disable=C0103,E1103,R0904

# Copyright (c) 2011-2013 Rackspace Hosting
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Tests for Rackspace legacy compute provider."""
import logging
import unittest

import mock
import mox

from checkmate.deployments import tasks
from checkmate import exceptions as cmexc
from checkmate import middleware as cmmid
from checkmate.providers.rackspace import compute_legacy
from checkmate import test

LOG = logging.getLogger(__name__)


class TestLegacyCompute(test.ProviderTester):
    """Test Legacy Compute Provider."""
    def setUp(self):
        test.ProviderTester.setUp(self)

    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    @mock.patch.object(tasks.resource_postback, 'delay')
    def test_create_server(self, mock_delay, mock_reset):
        provider = compute_legacy.Provider({})

        #Mock server
        server = mock.Mock()
        server.id = 'fake_server_id'
        server.status = 'BUILD'
        server.addresses = {
            'public': [
                '1.2.3.4'
            ],
            'private': [
                '5.6.7.8'
            ]
        }
        server.ip = '1.2.3.4'
        server.private_ip = '5.6.7.8'
        server.adminPass = 'password'

        #Mock image
        image = mock.Mock()
        image.id = 119

        #Mock flavor
        flavor = mock.Mock()
        flavor.id = 2

        #Create appropriate api mocks
        openstack_api_mock = mock.Mock()
        openstack_api_mock.servers = mock.Mock()
        openstack_api_mock.images = mock.Mock()
        openstack_api_mock.flavors = mock.Mock()

        openstack_api_mock.images.find.return_value = image
        openstack_api_mock.flavors.find.return_value = flavor
        openstack_api_mock.servers.create.return_value = server

        expected = {
            'resources': {
                '1': {
                    'status': 'BUILD',
                    'instance': {
                        'id': server.id,
                        'ip': server.ip,
                        'password': server.adminPass,
                        'private_ip': server.private_ip
                    }
                }
            }
        }

        context = {
            'deployment': 'DEP',
            'resource': '1',
            'tenant': 'TMOCK',
            'base_url': 'http://MOCK'
        }
        tasks.reset_failed_resource_task.delay(context['deployment'],
                                               context['resource'])

        mock_delay.return_value = True

        results = compute_legacy.create_server(
            context,
            name='fake_server',
            api_object=openstack_api_mock,
            flavor=2,
            files=None,
            image=119,
            ip_address_type='public',
            tags=provider.generate_resource_tag(
                context['base_url'],
                context['tenant'],
                context['deployment'],
                context['resource']
            )
        )

        self.assertDictEqual(results, expected)
        openstack_api_mock.servers.create.assert_called_with(
            image=119,
            flavor=2,
            meta={
                'RAX-CHECKMATE':
                'http://MOCK/TMOCK/deployments/DEP/resources/1'
            },
            name='fake_server',
            files=None
        )
        openstack_api_mock.images.find.assert_called_with(
            id=image.id
        )
        openstack_api_mock.flavors.find.assert_called_with(
            id=flavor.id
        )
        mock_delay.assert_called_with(
            context['deployment'],
            expected
        )


class TestLegacyGenerateTemplate(unittest.TestCase):
    """Test Legacy Compute Provider's region functions."""

    def setUp(self):
        self.mox = mox.Mox()
        self.deployment = self.mox.CreateMockAnything()
        self.deployment.get_setting('domain', default='checkmate.local',
                                    provider_key='rackspace.legacy',
                                    resource_type='compute',
                                    service_name='master'). \
            AndReturn("test.checkmate")
        self.deployment._constrained_to_one('master').AndReturn(True)

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_catalog_and_deployment_same(self):
        """Catalog and Deployment have matching regions."""
        catalog = {
            'lists': {
                'sizes': {
                    '2': {
                        'disk': 20,
                        'name': '512server',
                        'memory': 512
                    }
                },
                'types': {
                    '119': {
                        'os': 'Ubuntu11.10',
                        'name': 'Ubuntu11.10'
                    }
                },
                'regions': {
                    'ORD': 'http://some.endpoint'
                }
            }
        }
        provider = compute_legacy.Provider({})

        #Mock Base Provider, context and deployment
        context = cmmid.RequestContext()

        #Stub out provider calls
        self.mox.StubOutWithMock(provider, 'get_catalog')

        self.deployment.get_setting('region', resource_type='compute',
                                    service_name='master',
                                    provider_key=provider.key).AndReturn('ORD')
        self.deployment.get_setting('os', resource_type='compute',
                                    service_name='master',
                                    provider_key=provider.key,
                                    default=119).AndReturn('119')
        self.deployment.get_setting('memory', resource_type='compute',
                                    service_name='master',
                                    provider_key=provider.key,
                                    default=512).AndReturn('512')

        expected = [{
            'instance': {},
            'dns-name': 'master.test.checkmate',
            'type': 'compute',
            'provider': 'rackspace.legacy',
            'service': 'master',
            'flavor': '2',
            'image': '119',
            'region': 'ORD',
            'desired-state': {},
        }]

        provider.get_catalog(context).AndReturn(catalog)
        provider.get_catalog(context, type_filter="regions").AndReturn(catalog)

        self.mox.ReplayAll()
        results = provider.generate_template(self.deployment, 'compute',
                                             'master',
                                             context, 1, provider.key, None)

        self.assertListEqual(results, expected)
        self.mox.VerifyAll()

    def test_catalog_and_deployment_diff(self):
        """Catalog and Deployment have different regions."""
        catalog = {
            'lists': {
                'regions': {
                    'ORD': 'http://some.endpoint'
                }
            }
        }
        provider = compute_legacy.Provider({})

        #Mock Base Provider, context and deployment
        context = cmmid.RequestContext()

        #Stub out provider calls
        self.mox.StubOutWithMock(provider, 'get_catalog')
        provider.get_catalog(context).AndReturn(catalog)

        self.deployment.get_setting('region', resource_type='compute',
                                    service_name='master',
                                    provider_key=provider.key). \
            AndReturn('dallas')

        provider.get_catalog(context, type_filter="regions").AndReturn(catalog)

        self.mox.ReplayAll()
        try:
            provider.generate_template(self.deployment, 'compute',
                                       'master', context, 1, provider.key,
                                       None)
        except cmexc.CheckmateException:
            #pass
            self.mox.VerifyAll()

    def test_no_region(self):
        """No region specified in deployment or catalog."""
        catalog = {
            'lists': {
                'sizes': {
                    '2': {
                        'disk': 20,
                        'name': '512server',
                        'memory': 512
                    }
                },
                'types': {
                    '119': {
                        'os': 'Ubuntu11.10',
                        'name': 'Ubuntu11.10'
                    }
                }
            }
        }
        provider = compute_legacy.Provider({})

        #Mock Base Provider, context and deployment
        context = cmmid.RequestContext()

        #Stub out provider calls
        self.mox.StubOutWithMock(provider, 'get_catalog')

        self.deployment.get_setting('region', resource_type='compute',
                                    service_name='master',
                                    provider_key=provider.key).AndReturn(None)
        self.deployment.get_setting('os', resource_type='compute',
                                    service_name='master',
                                    provider_key=provider.key,
                                    default=119).AndReturn('119')
        self.deployment.get_setting('memory', resource_type='compute',
                                    service_name='master',
                                    provider_key=provider.key,
                                    default=512).AndReturn('512')

        expected = [{
            'instance': {},
            'dns-name': 'master.test.checkmate',
            'type': 'compute',
            'provider': 'rackspace.legacy',
            'flavor': '2',
            'image': '119',
            'service': 'master',
            'desired-state': {},
        }]

        provider.get_catalog(context).AndReturn(catalog)

        self.mox.ReplayAll()
        results = provider.generate_template(self.deployment, 'compute',
                                             'master',
                                             context, 1, provider.key, None)

        self.assertListEqual(results, expected)
        self.mox.VerifyAll()

    def test_deployment_region(self):
        """Region specified in deployment but not catalog."""
        catalog = {
            'lists': {
                'sizes': {
                    '2': {
                        'disk': 20,
                        'name': '512server',
                        'memory': 512
                    }
                },
                'types': {
                    '119': {
                        'os': 'Ubuntu11.10',
                        'name': 'Ubuntu11.10'
                    }
                }
            }
        }
        provider = compute_legacy.Provider({})

        #Mock Base Provider, context and deployment

        context = cmmid.RequestContext()

        #Stub out provider calls
        self.mox.StubOutWithMock(provider, 'get_catalog')

        self.deployment.get_setting('region', resource_type='compute',
                                    service_name='master',
                                    provider_key=provider.key) \
            .AndReturn('ORD')
        self.deployment.get_setting('os', resource_type='compute',
                                    service_name='master',
                                    provider_key=provider.key,
                                    default=119).AndReturn('119')
        self.deployment.get_setting('memory', resource_type='compute',
                                    service_name='master',
                                    provider_key=provider.key, default=512) \
            .AndReturn('512')

        expected = [{
            'instance': {},
            'dns-name': 'master.test.checkmate',
            'type': 'compute',
            'provider': 'rackspace.legacy',
            'service': 'master',
            'flavor': '2',
            'image': '119',
            'region': 'ORD',
            'desired-state': {},
        }]

        provider.get_catalog(context).AndReturn(catalog)
        provider.get_catalog(context, type_filter="regions").AndReturn(catalog)

        self.mox.ReplayAll()

        results = provider.generate_template(self.deployment, 'compute',
                                             'master',
                                             context, 1, provider.key, None)
        self.mox.VerifyAll()
        self.assertListEqual(results, expected)

    def test_region_supplied_as_airport_code(self):
        """Deployment region listed as airport code."""
        catalog = {
            'lists': {
                'sizes': {
                    '2': {
                        'disk': 20,
                        'name': '512server',
                        'memory': 512
                    }
                },
                'types': {
                    '119': {
                        'os': 'Ubuntu11.10',
                        'name': 'Ubuntu11.10'
                    }
                },
                'regions': {
                    'ORD': 'http://some.endpoint'
                }

            }
        }
        provider = compute_legacy.Provider({})

        context = cmmid.RequestContext()

        #Stub out provider calls
        self.mox.StubOutWithMock(provider, 'get_catalog')

        self.deployment.get_setting('region', resource_type='compute',
                                    service_name='master',
                                    provider_key=provider.key).AndReturn('ORD')
        self.deployment.get_setting('os', resource_type='compute',
                                    service_name='master',
                                    provider_key=provider.key, default=119). \
            AndReturn('119')
        self.deployment.get_setting('memory', resource_type='compute',
                                    service_name='master',
                                    provider_key=provider.key, default=512). \
            AndReturn('512')

        expected = [
            {
                'instance': {},
                'dns-name': 'master.test.checkmate',
                'type': 'compute',
                'provider': 'rackspace.legacy',
                'service': 'master',
                'flavor': '2',
                'image': '119',
                'region': 'ORD',
                'desired-state': {},
            }
        ]

        provider.get_catalog(context).AndReturn(catalog)
        provider.get_catalog(context, type_filter="regions").AndReturn(catalog)

        self.mox.ReplayAll()
        results = provider.generate_template(self.deployment, 'compute',
                                             'master',
                                             context, 1, provider.key, None)

        self.assertListEqual(results, expected)
        self.mox.VerifyAll()


if __name__ == '__main__':
    import sys

    test.run_with_params(sys.argv[:])
