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
import mock
import unittest

from checkmate.providers import base
from checkmate.providers.rackspace import compute


class TestGetApiInfo(unittest.TestCase):
    """Class for testing _get_api_info method."""

    def setUp(self):
        """Sets up context and kwargs for re-use."""
        self.context = base.middleware.RequestContext(**{'region': 'SYD'})
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
        mock_base = mock.Mock(id="B", metadata={'image_type': 'base'})
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
                },
            },
        }

        results = compute.provider._get_images_and_types("localhost", "token")
        self.assertEqual(results, expected)


class TestImageDetection(unittest.TestCase):
    def test_blank(self):
        detected = compute.provider.detect_image('')
        self.assertEqual(detected, {})

    def test_rackspace_metadata(self):
        metadata = {
            'os_distro': 'ubuntu',
            'os_version': '12.04',
        }
        detected = compute.provider.detect_image('', metadata=metadata)
        self.assertEqual(detected['os'], 'Ubuntu 12.04')
        self.assertEqual(detected['type'], 'linux')

    def test_openstack_metadata(self):
        metadata = {
            'org.openstack__1__os_distro': 'org.ubuntu',
            'org.openstack__1__os_version': '12.04',
        }
        detected = compute.provider.detect_image('', metadata=metadata)
        self.assertEqual(detected['os'], 'Ubuntu 12.04')
        self.assertEqual(detected['type'], 'linux')

    def test_openstack_metadata_bad_case(self):
        metadata = {
            'org.openstack__1__os_distro': 'Org.Ubuntu',
            'org.openstack__1__os_version': '12.04',
        }
        detected = compute.provider.detect_image('', metadata=metadata)
        self.assertEqual(detected['os'], 'Ubuntu 12.04')
        self.assertEqual(detected['type'], 'linux')

    def test_openstack_metadata_windows_r2(self):
        metadata = {
            'org.openstack__1__os_distro': 'org.microsoft.server',
            'org.openstack__1__os_version': '2008.2',
        }
        detected = compute.provider.detect_image('', metadata=metadata)
        self.assertEqual(detected['os'],
                         'Microsoft Windows Server 2008 R2 SP1')
        self.assertEqual(detected['type'], 'windows')

    def test_openstack_metadata_windows(self):
        metadata = {
            'org.openstack__1__os_distro': 'org.microsoft.server',
            'org.openstack__1__os_version': '2012',
        }
        detected = compute.provider.detect_image('', metadata=metadata)
        self.assertEqual(detected['os'], 'Microsoft Windows Server 2012')
        self.assertEqual(detected['type'], 'windows')

    def test_name_codename(self):
        detected = compute.provider.detect_image("My 'precise' image")
        self.assertEqual(detected['os'], 'Ubuntu 12.04')
        self.assertEqual(detected['type'], 'linux')

    def test_name_fullname(self):
        detected = compute.provider.detect_image("Ubuntu 12.04 image")
        self.assertEqual(detected['os'], 'Ubuntu 12.04')
        self.assertEqual(detected['type'], 'linux')

    def test_known_name_version(self):
        detected = compute.provider.detect_image("vagrant-ubuntu-x64-13.10")
        self.assertEqual(detected['os'], 'Ubuntu 13.10')
        self.assertEqual(detected['type'], 'linux')

    def test_rackspace_image(self):
        detected = compute.provider.detect_image("OtherOS 10.4 LTS (code "
                                                 "red)")
        self.assertEqual(detected['os'], 'OtherOS 10.4')
        self.assertEqual(detected['type'], 'linux')

    def test_inova_image(self):
        detected = compute.provider.detect_image("OtherOS 10.4 LTS")
        self.assertEqual(detected['os'], 'OtherOS 10.4')
        self.assertEqual(detected['type'], 'linux')


class EventletGreenpile(list):
    """Class to facilitate testing greenpile jobs iteration."""
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
