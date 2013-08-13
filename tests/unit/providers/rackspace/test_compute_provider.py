# pylint: disable=C0103,C0111,R0201,R0903,R0904,W0212,W0232,W0201
# encoding: utf-8
'''Module for testing Rackspace Compute Provider.'''
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

    @mock.patch.object(compute.eventlet, 'GreenPile')
    @mock.patch.object(compute.Provider, 'find_url')
    def test_context_success(self, mock_find_url, mock_eventlet):
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
                        'name': u'Windows Server 2012 + SQL Server 2012 '
                    }
                }
            }
        })
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

        results = compute.Provider._get_api_info(self.context)
        self.assertEqual(results, expected)
        mock_find_url.assert_called_with(None, self.context['region'])
        mock_eventlet.assert_called_with(2)
        self.assertEqual(mock_jobs.spawn.call_count, 2)

    @mock.patch.object(compute.eventlet, 'GreenPile')
    @mock.patch.object(compute.Provider, 'find_url')
    def test_kwargs_success(self, mock_find_url, mock_eventlet):
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
        results = compute.Provider._get_api_info(self.context, **self.kwargs)
        self.assertEqual(results, expected)
        mock_find_url.assert_called_with(None, self.kwargs['region'].upper())
        mock_eventlet.assert_called_with(2)
        self.assertEqual(mock_jobs.spawn.call_count, 2)

    @mock.patch.object(compute.eventlet, 'GreenPile')
    @mock.patch.object(compute.Provider, 'find_url')
    @mock.patch.object(compute.Provider, 'get_regions')
    @mock.patch.object(compute.LOG, 'warning')
    def test_no_region(self, mock_logger, mock_get_regions, mock_find_url,
                       mock_eventlet):
        """Verifies method calls with no region and dicts merged."""
        self.context['region'] = None
        self.kwargs['region'] = None
        mock_get_regions.return_value = ['ORD', 'DFW', 'IAD']
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
        results = compute.Provider._get_api_info(self.context, **self.kwargs)
        mock_eventlet.assert_called_with(6)
        mock_get_regions.assert_called_with(None, 'cloudServersOpenStack')
        mock_logger.assert_called_with('Region not found in context or kwargs.')
        self.assertEqual(mock_find_url.mock_calls, expected_find_urls)
        self.assertEqual(mock_jobs.spawn.call_count, 6)
        self.assertEqual(results, expected)

    @mock.patch.object(compute.LOG, 'warning')
    @mock.patch.object(compute.eventlet, 'GreenPile')
    @mock.patch.object(compute.Provider, 'find_url')
    def test_no_urls(self, mock_find_url, mock_eventlet, mock_logger):
        """Verifies method calls when no urls returned."""
        mock_find_url.return_value = None
        mock_jobs = EventletGreenpile()
        mock_jobs.spawn = mock.Mock()
        mock_eventlet.return_value = mock_jobs
        compute.Provider._get_api_info(self.context)
        mock_logger.assert_called_with('Failed to find compute endpoint for '
                                       '%s in region %s', None, 'SYD')


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
