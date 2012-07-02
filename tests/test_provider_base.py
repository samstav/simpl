#!/usr/bin/env python
import unittest2 as unittest

from checkmate.providers.base import ProviderBase
from checkmate.utils import yaml_to_dict


class TestProviderBase(unittest.TestCase):
    def test_get_setting(self):
        """Test the get_setting function"""
        deployment = yaml_to_dict("""
                blueprint:
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
                        memory: 4 Gb
                  services:
                    web:
                      compute:
                        case-whitespace-test: 512mb
                        gigabyte-test: 8 gigabytes
                        mb-test: 512 Mb
                        memory: 2 Gb
                        number-only-test: 512
            """)
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
