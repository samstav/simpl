# pylint: disable=C0103,C0302,E1101,E1103,R0904,R0201,W0212,W0613

# Copyright (c) 2011-2015 Rackspace US, Inc.
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
# pylint: disable=C0103,C0111,E1101,E1103,R0201,R0903,R0904,W0201,W0212,W0232
import os

import mock
import unittest

from checkmate.providers import base
from checkmate.providers.rackspace import compute
from checkmate import utils


class TestGetApiInfo(unittest.TestCase):

    """Class for testing _get_api_info method."""

    def setUp(self):
        """Sets up context and kwargs for re-use."""
        self.context = base.middleware.RequestContext(region='SYD')
        self.kwargs = {'region': 'iad'}

    @mock.patch.object(compute.provider.eventlet, 'GreenPile')
    @mock.patch.object(compute.provider.Provider, 'find_url')
    @mock.patch.object(compute.provider.CONFIG, 'eventlet')
    def test_context_success(self, mock_config, mock_find_url, mock_eventlet):
        """Verifies method calls on success with context['region']."""
        mock_find_url.return_value = 'http://testurl.com'
        mock_jobs = EventletGreenpile()
        mock_jobs.spawn = mock.Mock()
        mock_jobs.append({
            'compute': {
                'linux_instance': {
                    'id': 'linux_instance'
                }
            }
        })
        mock_jobs.append({
            'lists': {
                'images': {
                    u'09149fae-2236-42d6-9b4c-ba34a53a2d70': {
                        'name': u'Windows Server 2012 + SQL Server 2012'
                    }
                }
            }
        })
        mock_config.return_value = True
        mock_eventlet.return_value = mock_jobs
        expected = {
            'compute': {
                'linux_instance': {
                    'id': 'linux_instance'
                }
            },
            'lists': {
                'images': {
                    u'09149fae-2236-42d6-9b4c-ba34a53a2d70': {
                        'name': u'Windows Server 2012 + SQL Server 2012'
                    }
                }
            }
        }

        results = compute.Provider._get_api_info(self.context)
        self.assertEqual(results, expected)
        mock_find_url.assert_called_with(None, self.context['region'])
        mock_eventlet.assert_called_with(2)
        self.assertEqual(mock_jobs.spawn.call_count, 2)

    @mock.patch.object(compute.provider.eventlet, 'GreenPile')
    @mock.patch.object(compute.provider.Provider, 'find_url')
    @mock.patch.object(compute.provider.CONFIG, 'eventlet')
    def test_kwargs_success(self, mock_config, mock_find_url, mock_eventlet):
        """Verifies method calls on success with kwargs['region']."""
        mock_find_url.return_value = 'http://testurl.com'
        mock_jobs = EventletGreenpile()
        mock_jobs.spawn = mock.Mock()
        mock_jobs.append({
            'compute': {
                'linux_instance': {
                    'id': 'linux_instance'
                }
            }
        })
        mock_jobs.append({
            'lists': {
                'images': {
                    u'09149fae-2236-42d6-9b4c-ba34a53a2d70': {
                        'name': u'Windows Server 2012 + SQL Server 2012 '
                    }
                }
            }
        })
        mock_config.return_value = True
        mock_eventlet.return_value = mock_jobs
        expected = {
            'compute': {
                'linux_instance': {
                    'id': 'linux_instance'
                }
            },
            'lists': {
                'images': {
                    u'09149fae-2236-42d6-9b4c-ba34a53a2d70': {
                        'name': u'Windows Server 2012 + SQL Server 2012 '
                    }
                }
            }
        }
        self.context['region'] = None
        results = compute.provider.Provider._get_api_info(
            self.context, **self.kwargs)
        self.assertEqual(results, expected)
        mock_find_url.assert_called_with(None, self.kwargs['region'].upper())
        mock_eventlet.assert_called_with(2)
        self.assertEqual(mock_jobs.spawn.call_count, 2)

    @mock.patch.object(compute.provider.eventlet, 'GreenPile')
    @mock.patch.object(compute.provider.Provider, 'find_url')
    @mock.patch.object(compute.provider.Provider, 'get_regions')
    @mock.patch.object(compute.provider.LOG, 'warning')
    @mock.patch.object(compute.provider.CONFIG, 'eventlet')
    def test_no_region(self, mock_config, mock_logger, mock_get_regions,
                       mock_find_url, mock_eventlet):
        """Verifies method calls with no region and dicts merged."""
        self.context['region'] = None
        self.kwargs['region'] = None
        mock_get_regions.return_value = ['ORD', 'DFW', 'IAD']
        mock_find_url.return_value = 'http://testurl.com'
        mock_config.return_value = True
        mock_jobs = EventletGreenpile()
        mock_jobs.spawn = mock.Mock()
        mock_jobs.append({
            'compute': {
                'linux_instance': {
                    'id': 'linux_instance'
                }
            }
        })
        mock_jobs.append({
            'lists': {
                'images': {
                    u'09149fae-2236-42d6-9b4c-ba34a53a2d70': {
                        'name': u'Windows Server 2012 + SQL Server 2012 '
                    }
                }
            }
        })
        mock_jobs.append({
            'compute': {
                'windows_instance': {
                    'id': 'windows_instance'
                }
            }
        })
        mock_jobs.append({
            'lists': {
                'images': {
                    u'asdfae-2236-42d6-9b4c-ba34a53a2d70': {
                        'name': u'Linux Server 2012 + SQL Server 2012 '
                    }
                }
            }
        })
        mock_jobs.append({
            'compute': {
                'freebsd_instance': {
                    'id': 'freebsd_instance'
                }
            }
        })
        mock_jobs.append({
            'lists': {
                'images': {
                    u'poiuyae-2236-42d6-9b4c-ba34a53a2d70': {
                        'name': u'FreeBSD Server 2012 + SQL Server 2012 '
                    }
                }
            }
        })
        mock_eventlet.return_value = mock_jobs
        expected = {
            'compute': {
                'linux_instance': {
                    'id': 'linux_instance'
                },
                'windows_instance': {
                    'id': 'windows_instance'
                },
                'freebsd_instance': {
                    'id': 'freebsd_instance'
                }
            },
            'lists': {
                'images': {
                    u'09149fae-2236-42d6-9b4c-ba34a53a2d70': {
                        'name': u'Windows Server 2012 + SQL Server 2012 '
                    },
                    u'asdfae-2236-42d6-9b4c-ba34a53a2d70': {
                        'name': u'Linux Server 2012 + SQL Server 2012 '
                    },
                    u'poiuyae-2236-42d6-9b4c-ba34a53a2d70': {
                        'name': u'FreeBSD Server 2012 + SQL Server 2012 '
                    }
                }
            }
        }
        expected_find_urls = [
            mock.call(None, 'ORD'),
            mock.call(None, 'DFW'),
            mock.call(None, 'IAD')
        ]
        results = compute.provider.Provider._get_api_info(
            self.context, **self.kwargs)
        mock_eventlet.assert_called_with(6)
        mock_get_regions.assert_called_with(
            None, resource_type='compute',
            service_name='cloudServersOpenStack')
        mock_logger.assert_called_with('Region not found in context or '
                                       'kwargs.')
        self.assertEqual(mock_find_url.mock_calls, expected_find_urls)
        self.assertEqual(mock_jobs.spawn.call_count, 6)
        self.assertEqual(results, expected)

    @mock.patch.object(compute.provider.LOG, 'warning')
    @mock.patch.object(compute.provider.eventlet, 'GreenPile')
    @mock.patch.object(compute.provider.Provider, 'find_url')
    def test_no_urls(self, mock_find_url, mock_eventlet, mock_logger):
        """Verifies method calls when no urls returned."""
        mock_find_url.return_value = None
        mock_jobs = EventletGreenpile()
        mock_jobs.spawn = mock.Mock()
        mock_eventlet.return_value = mock_jobs
        compute.provider.Provider._get_api_info(self.context)
        mock_logger.assert_called_with('Failed to find compute endpoint for '
                                       '%s in region %s', None, 'SYD')

    @mock.patch.object(compute.provider.CLIENT, 'Client')
    def test_skip_snapshots(self, mock_client):
        """Verifies snapshots are ignored."""
        mock_snapshot = mock.Mock(id="A", metadata={'image_type': 'snapshot'})
        mock_snapshot.configure_mock(name="Ubuntu 12.04 Snapshot")
        mock_base = mock.Mock(id="B", metadata={
            'image_type': 'base',
            'vm_mode': 'hvm',
            'flavor_classes': '*,!onmetal'
        })
        mock_base.configure_mock(name="Ubuntu 12.04 Base")

        mock_list = mock.Mock(return_value=[mock_base, mock_snapshot])
        mock_images = mock.Mock(list=mock_list)
        mock_api = mock.Mock(images=mock_images)
        mock_client.return_value = mock_api

        expected = {
            'images': {'B': {'name': 'Ubuntu 12.04 Base'}},
            'types': {
                'B': {
                    'name': 'Ubuntu 12.04 Base',
                    'os': 'Ubuntu 12.04',
                    'type': 'linux',
                    'constraints': {
                        'auto_disk_config': None,
                        'flavor_classes': '*,!onmetal',
                        'vm_mode': 'hvm',
                    },
                },
            },
        }

        results = compute.provider._get_images_and_types("localhost", "token")
        self.assertEqual(results, expected)


class TestImageDetection(unittest.TestCase):
    def test_blank(self):
        detected = compute.provider.detect_image_os('')
        self.assertEqual(detected, {})

    def test_rackspace_metadata(self):
        metadata = {
            'os_distro': 'ubuntu',
            'os_version': '12.04',
        }
        detected = compute.provider.detect_image_os('', metadata=metadata)
        self.assertEqual(detected['os'], 'Ubuntu 12.04')
        self.assertEqual(detected['type'], 'linux')

    def test_openstack_metadata(self):
        metadata = {
            'org.openstack__1__os_distro': 'org.ubuntu',
            'org.openstack__1__os_version': '12.04',
        }
        detected = compute.provider.detect_image_os('', metadata=metadata)
        self.assertEqual(detected['os'], 'Ubuntu 12.04')
        self.assertEqual(detected['type'], 'linux')

    def test_openstack_metadata_bad_case(self):
        metadata = {
            'org.openstack__1__os_distro': 'Org.Ubuntu',
            'org.openstack__1__os_version': '12.04',
        }
        detected = compute.provider.detect_image_os('', metadata=metadata)
        self.assertEqual(detected['os'], 'Ubuntu 12.04')
        self.assertEqual(detected['type'], 'linux')

    def test_openstack_metadata_windows_r2(self):
        metadata = {
            'org.openstack__1__os_distro': 'org.microsoft.server',
            'org.openstack__1__os_version': '2008.2',
        }
        detected = compute.provider.detect_image_os('', metadata=metadata)
        self.assertEqual(detected['os'],
                         'Microsoft Windows Server 2008 R2 SP1')
        self.assertEqual(detected['type'], 'windows')

    def test_openstack_metadata_windows(self):
        metadata = {
            'org.openstack__1__os_distro': 'org.microsoft.server',
            'org.openstack__1__os_version': '2012',
        }
        detected = compute.provider.detect_image_os('', metadata=metadata)
        self.assertEqual(detected['os'], 'Microsoft Windows Server 2012')
        self.assertEqual(detected['type'], 'windows')

    def test_name_codename(self):
        detected = compute.provider.detect_image_os("My 'precise' image")
        self.assertEqual(detected['os'], 'Ubuntu 12.04')
        self.assertEqual(detected['type'], 'linux')

    def test_name_fullname(self):
        detected = compute.provider.detect_image_os("Ubuntu 12.04 image")
        self.assertEqual(detected['os'], 'Ubuntu 12.04')
        self.assertEqual(detected['type'], 'linux')

    def test_known_name_version(self):
        detected = compute.provider.detect_image_os("vagrant-ubuntu-x64-13.10")
        self.assertEqual(detected['os'], 'Ubuntu 13.10')
        self.assertEqual(detected['type'], 'linux')

    def test_rackspace_image(self):
        detected = compute.provider.detect_image_os("OtherOS 10.4 LTS (code "
                                                    "red)")
        self.assertEqual(detected['os'], 'OtherOS 10.4')
        self.assertEqual(detected['type'], 'linux')

    def test_inova_image(self):
        detected = compute.provider.detect_image_os("OtherOS 10.4 LTS")
        self.assertEqual(detected['os'], 'OtherOS 10.4')
        self.assertEqual(detected['type'], 'linux')


class EventletGreenpile(list):

    """Class to facilitate testing greenpile jobs iteration."""


class TestFlavorClasses(unittest.TestCase):

    flavor_totals = {
        'standard1': 7,
        'general1': 4,
        'performance1': 4,
        'performance2': 5,
        'onmetal': 3,
        'io1': 5,
        'compute1': 5,
        'memory1': 5,
    }

    @classmethod
    def setUpClass(cls):
        path = os.path.join(os.path.dirname(__file__), 'nova_catalog.yaml')
        with open(path, 'r') as handle:
            cls.catalog = utils.yaml_to_dict(handle.read())
        cls.flavors = cls.catalog['lists']['sizes']
        cls.images = cls.catalog['lists']['types']

    def test_catalog(self):
        """Catalog parses and is used if supplied as override."""
        provider = compute.provider.Provider({'catalog': self.catalog})
        self.assertItemsEqual(provider.get_catalog({}).keys(),
                              ['compute', 'lists'])
        self.assertEqual(provider.get_catalog({}), self.catalog)
        self.assertEqual(len(provider.get_catalog({})['lists']['types']), 61)
        self.assertEqual(len(provider.get_catalog({})['lists']['sizes']), 38)

    def test_flavor_class_filter(self):
        """Filtering by class works."""
        for flavor_class, count in self.flavor_totals.items():
            flavors = compute.provider.filter_flavors(
                self.flavors, class_rules=flavor_class)
            self.assertEqual(len(flavors), count)

    def test_flavor_class_not_filter(self):
        """Filtering by !class works."""
        flavors = compute.provider.filter_flavors(
            self.flavors, class_rules='*,!standard1')
        self.assertEqual(len(flavors),
                         len(self.flavors) - self.flavor_totals['standard1'])

    def test_flavor_disk_filter(self):
        """Filtering by disk size works."""
        flavors = compute.provider.filter_flavors(self.flavors, min_disk=30)
        self.assertTrue(all(f['disk'] >= 30 for f in flavors.values()))
        self.assertGreater(len(flavors), 0)

    def test_flavor_diskless_filter(self):
        """Test that include_diskless returns zero-sized flavors."""
        diskless = compute.provider.filter_flavors(self.flavors, min_disk=40,
                                                   include_diskless=True)
        self.assertTrue(all(f['disk'] == 0 or f['disk'] >= 40
                            for f in diskless.values()))
        self.assertTrue(any(f['disk'] == 0 for f in diskless.values()))

    def test_all_flavors(self):
        """Check all flavors have values we expect and have accounted for."""
        all_flavors = compute.provider.filter_flavors(
            self.flavors, class_rules=None)
        self.assertEqual(len(all_flavors), 38)
        allowed = self.flavor_totals.keys()
        for flavor in all_flavors.itervalues():
            self.assertIn(flavor['extra']['class'], allowed)

    def test_flavor_filtering(self):
        """Filtering for class should work."""
        onmetal = compute.provider.filter_flavors(
            self.flavors, class_rules='onmetal')
        large_mem = compute.provider.filter_flavors(
            self.flavors, min_memory=64 * 1024)
        sixteen_cores = compute.provider.filter_flavors(
            self.flavors, min_cores=16)
        big_disk = compute.provider.filter_flavors(
            self.flavors, min_disk=40)
        targetted = compute.provider.filter_flavors(
            self.flavors, min_cores=32, min_memory=196 * 1024)

        self.assertEqual(len(onmetal), 3)
        self.assertTrue(all(f['extra']['policy_class'] == 'onmetal_flavor'
                            for f in onmetal.values()))
        self.assertEqual(len(large_mem), 8)
        self.assertEqual(len(sixteen_cores), 13)
        self.assertEqual(len(big_disk), 22)
        self.assertEqual(len(targetted), 1)

    def test_image_filtering(self):
        """Filtering for flavor class should work."""
        standard1 = compute.provider.filter_images(
            self.images, flavor_class='standard1')
        self.assertEqual(len(standard1), 49)
        modes = set(f['constraints']['vm_mode'] for f in standard1.values())
        self.assertTrue(all(m in {'xen', 'hvm', 'windows'} for m in modes))

        general1 = compute.provider.filter_images(
            self.images, flavor_class='general1')
        self.assertEqual(len(general1), 49)
        modes = set(f['constraints']['vm_mode'] for f in general1.values())
        self.assertTrue(all(m in {'xen', 'hvm', 'windows'} for m in modes))

        io1 = compute.provider.filter_images(
            self.images, flavor_class='io1')
        self.assertEqual(len(io1), 39)
        modes = set(f['constraints']['vm_mode'] for f in io1.values())
        self.assertTrue(all(m in {'hvm', 'windows'} for m in modes))

        memory1 = compute.provider.filter_images(
            self.images, flavor_class='memory1')
        self.assertEqual(len(memory1), 39)
        modes = set(f['constraints']['vm_mode'] for f in memory1.values())
        self.assertTrue(all(m in {'hvm', 'windows'} for m in modes))

        compute1 = compute.provider.filter_images(
            self.images, flavor_class='compute1')
        self.assertEqual(len(compute1), 39)
        modes = set(f['constraints']['vm_mode'] for f in compute1.values())
        self.assertTrue(all(m in {'hvm', 'windows'} for m in modes))

        onmetal = compute.provider.filter_images(
            self.images, flavor_class='onmetal')
        self.assertEqual(len(onmetal), 12)
        self.assertTrue(all(f['constraints']['vm_mode'] == 'metal'
                            for f in onmetal.values()))

    def test_image_filtering_vm_mode(self):
        """Filtering for flavor class should work with vm_mode."""
        standard1 = compute.provider.filter_images(
            self.images, flavor_class='standard1', vm_mode='hvm')
        self.assertEqual(len(standard1), 22)
        modes = set(f['constraints']['vm_mode'] for f in standard1.values())
        self.assertTrue(all(m == 'hvm' for m in modes))


class TestImageFlavorMatching(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Subset of real Rackspace Nova catalog flavors
        flavors = utils.yaml_to_dict("""
            '2':
              cores: 1
              disk: 20
              extra:
                class: standard1
                disk_io_index: '2'
                number_of_data_disks: '0'
                policy_class: standard_flavor
              memory: 512
              name: 512MB Standard Instance
              network: 80.0
            compute1-15:
              cores: 8
              disk: 0
              extra:
                class: compute1
                disk_io_index: '-1'
                number_of_data_disks: '0'
                policy_class: compute_flavor
              memory: 15360
              name: 15 GB Compute v1
              network: 1250.0
            general1-1:
              cores: 1
              disk: 20
              extra:
                class: general1
                disk_io_index: '40'
                number_of_data_disks: '0'
                policy_class: general_flavor
              memory: 1024
              name: 1 GB General Purpose v1
              network: 200.0
            io1-15:
              cores: 4
              disk: 40
              extra:
                class: io1
                disk_io_index: '40'
                number_of_data_disks: '1'
                policy_class: io_flavor
              memory: 15360
              name: 15 GB I/O v1
              network: 1250.0
            memory1-120:
              cores: 16
              disk: 0
              extra:
                class: memory1
                disk_io_index: '-1'
                number_of_data_disks: '0'
                policy_class: memory_flavor
              memory: 122880
              name: 120 GB Memory v1
              network: 5000.0
            onmetal-compute1:
              cores: 20
              disk: 32
              extra:
                class: onmetal
                policy_class: onmetal_flavor
                quota_resources: "instances=onmetal-compute-v1-instances,
                    ram=onmetal-compute-v1-ram"
              memory: 32768
              name: OnMetal Compute v1
              network: 10000.0
            performance1-1:
              cores: 1
              disk: 20
              extra:
                class: performance1
                disk_io_index: '40'
                number_of_data_disks: '0'
                policy_class: performance_flavor
                resize_policy_class: performance_flavor
              memory: 1024
              name: 1 GB Performance
              network: 200.0
            performance2-120:
              cores: 32
              disk: 40
              extra:
                class: performance2
                disk_io_index: '80'
                number_of_data_disks: '4'
                policy_class: performance_flavor
                resize_policy_class: performance_flavor
              memory: 122880
              name: 120 GB Performance
              network: 10000.0
        """)
        cls.standard = flavors['2']  # deprecated flavor class
        cls.general1 = flavors['general1-1']
        cls.perf1 = flavors['performance1-1']  # deprecated flavor class
        cls.perf2 = flavors['performance2-120']  # deprecated flavor class
        cls.compute1 = flavors['compute1-15']
        cls.memory1 = flavors['memory1-120']
        cls.io1 = flavors['io1-15']
        cls.onmetal = flavors['onmetal-compute1']

        # Subset of real Rackspace Nova catalog images
        ubuntu_images = utils.yaml_to_dict("""
            00a5dffd-1f9a-47a8-9ccc-7267a362a9da:
              constraints:
                auto_disk_config: 'True'
                flavor_classes: '*,!io1,!memory1,!compute1,!onmetal'
                vm_mode: xen
              name: Ubuntu 14.04 LTS (Trusty Tahr) (PV)
              os: Ubuntu 14.04
              type: linux
            1f097471-f0f4-4c3b-ac24-fdb1d897b8c0:
              constraints:
                auto_disk_config: disabled
                flavor_classes: onmetal
                vm_mode: metal
              name: OnMetal - Ubuntu 14.04 LTS (Trusty Tahr)
              os: Ubuntu 14.04
              type: linux
            714affe2-5b9b-4c9a-b513-2e2f86e91df8:
              constraints:
                auto_disk_config: disabled
                flavor_classes: '*,!onmetal'
                vm_mode: hvm
              name: Ubuntu 14.04 LTS (Trusty Tahr) (PVHVM)
              os: Ubuntu 14.04
              type: linux
        """)
        cls.xen_1404 = ubuntu_images['00a5dffd-1f9a-47a8-9ccc-7267a362a9da']
        cls.metal_1404 = ubuntu_images['1f097471-f0f4-4c3b-ac24-fdb1d897b8c0']
        cls.hvm_1404 = ubuntu_images['714affe2-5b9b-4c9a-b513-2e2f86e91df8']

    def test_standard_image(self):
        """Images marked 'xen' work except on metal and performance."""
        is_compatible = compute.provider.is_compatible

        # Accepts hvm and xen
        self.assertTrue(is_compatible(self.xen_1404, self.general1))
        # Require hvm
        self.assertFalse(is_compatible(self.xen_1404, self.compute1))
        self.assertFalse(is_compatible(self.xen_1404, self.io1))
        self.assertFalse(is_compatible(self.xen_1404, self.memory1))
        # Requires metal
        self.assertFalse(is_compatible(self.xen_1404, self.onmetal))

        # deprecated flavor classes
        self.assertTrue(is_compatible(self.xen_1404, self.standard))
        self.assertTrue(is_compatible(self.xen_1404, self.perf1))
        self.assertTrue(is_compatible(self.xen_1404, self.perf2))

    def test_pvhvm_image(self):
        """Images marked 'hvm' work everywhere except on metal."""
        is_compatible = compute.provider.is_compatible

        # Accepts hvm and xen
        self.assertTrue(is_compatible(self.hvm_1404, self.general1))
        # Require hvm
        self.assertTrue(is_compatible(self.hvm_1404, self.compute1))
        self.assertTrue(is_compatible(self.hvm_1404, self.io1))
        self.assertTrue(is_compatible(self.hvm_1404, self.memory1))
        # Requires metal
        self.assertFalse(is_compatible(self.hvm_1404, self.onmetal))

        # deprecated flavor classes
        self.assertTrue(is_compatible(self.hvm_1404, self.standard))
        self.assertTrue(is_compatible(self.hvm_1404, self.perf1))
        self.assertTrue(is_compatible(self.hvm_1404, self.perf2))

    def test_onmetal_image(self):
        """Images marked 'metal' only work on onmetal flavors."""
        is_compatible = compute.provider.is_compatible

        # Accepts hvm and xen
        self.assertFalse(is_compatible(self.metal_1404, self.general1))
        # Require hvm
        self.assertFalse(is_compatible(self.metal_1404, self.compute1))
        self.assertFalse(is_compatible(self.metal_1404, self.io1))
        self.assertFalse(is_compatible(self.metal_1404, self.memory1))
        # Requires metal
        self.assertTrue(is_compatible(self.metal_1404, self.onmetal))

        # deprecated flavor classes
        self.assertFalse(is_compatible(self.metal_1404, self.standard))
        self.assertFalse(is_compatible(self.metal_1404, self.perf1))
        self.assertFalse(is_compatible(self.metal_1404, self.perf2))

    def test_mismatch_on_disk(self):
        pass

    def test_match_on_memory(self):
        pass

    def test_match_on_hypervisor(self):
        pass

    def test_match_on_cpu(self):
        pass

    def test_match_on_two(self):
        pass

    def test_match_on_all(self):
        pass

    def test_match_onmetal_image(self):
        pass

    def test_match_hpv_image(self):
        pass

    def test_match_xen_image(self):
        pass


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
