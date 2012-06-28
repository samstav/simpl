#!/usr/bin/env python
import json
import unittest2 as unittest

from checkmate.providers.base import ProviderBase


class TestProviderBase(unittest.TestCase):
    def test_get_setting(self):
        """Test the get_setting function"""
        deployment = {
              'blueprint': {
                'options': {
                    'my_server_type': {
                        'constrains': [dict(service='web',
                                            resource_type='compute',
                                            setting='os')]
                    }
                }
              },
              'inputs': {
                'blueprint': {
                    'domain': 'example.com',
                    'my_server_type': 'Ubuntu 11.10'
                    },
                'services': {
                    'web': {
                        'compute': {
                            'memory': '2 Gb',
                            'number-only-test': 512,
                            'mb-test': '512 Mb',
                            'case-whitespace-test': '512mb',
                            'gigabyte-test': '8 gigabytes',
                            }
                        }
                    },
                'providers': {
                    'base': {
                        'compute': {
                            'memory': '4 Gb'
                            }
                        }
                    },
              },
            }
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
                }
            ]
        base = ProviderBase({'provides': ['compute']})
        for test in cases:
            value = base.get_deployment_setting(deployment, test['name'],
                    service=test.get('service'),
                    resource_type=test.get('type'))
            self.assertEquals(value, test['expected'], test['case'])


if __name__ == '__main__':
    unittest.main()
