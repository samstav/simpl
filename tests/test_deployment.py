#!/usr/bin/env python
import logging
import unittest2 as unittest

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate.deployment import Deployment
from checkmate.middleware import RequestContext
from checkmate.providers.opscode import solo

class TestDeployment(unittest.TestCase):
    def test_create_resource_template(self):
        """Test that a new resource dict is added to the deployment"""
        definition = {'connections':
                      {'host:linux': {'direction': 'outbound',
                                      'extra-key': 'host:linux',
                                      'interface': 'linux',
                                      'provides-key': 'compute:linux',
                                      'relation': 'host',
                                      'requires-key': 'host:linux',
                                      'service': 'database'}},
                      'host-keys': ['host:linux'],
                      'id': 'mysql',
                      'provider': 'opscode.solo',
                      'provider-key': 'chef-solo',
                      'provides': {'database:mysql':
                                   {'interface': 'mysql',
                                    'resource_type': 'database'}},
                      'requires': {'host:linux':
                                   {'interface': 'linux',
                                    'relation': 'host',
                                    'satisfied-by':
                                    {'component': 'linux_instance',
                                     'name': 'host:linux',
                                     'provides-key': 'compute:linux',
                                     'service': 'database'}}}}
        content = {'blueprint':
                   {'description': 'Deploy a MySQL server',
                    'id': 'D1CC995AE7634ED495CD0F5C8ED197E0',
                    'name': 'MySQL on VM',
                    'options':
                    {'os':
                     {'choice': ['Ubuntu 12.04'],
                      'constrains': [{'resource_type': 'compute',
                                      'service': 'database',
                                      'setting': 'os'}],
                      'default': 'Ubuntu 12.04',
                      'description':
                      'The operating system for the all servers.',
                      'label': 'Operating System',
                      'type': 'select'},
                     'region': {'choice': ['DFW', 'ORD', 'LON'],
                                'default': 'ORD',
                                'label': 'Region',
                                'required': True,
                                'type': 'select'},
                     'server_size': {'choice': [{'name': '512 Mb',
                                                 'value': 512},
                                                {'name': '1 Gb',
                                                 'value': 1024},
                                                {'name': '2 Gb',
                                                 'value': 2048},
                                                {'name': '4 Gb',
                                                 'value': 4096},
                                                {'name': '8 Gb',
                                                 'value': 8092},
                                                {'name': '16 Gb',
                                                 'value': 16384},
                                                {'name': '30 Gb',
                                                 'value': 30720}],
                                     'constrains':
                                     [{'resource_type': 'compute',
                                       'service': 'database',
                                       'setting': 'memory'}],
                                     'default': 512,
                                     'description': 'The size of the'
                                     'database instances in MB of RAM.',
                                     'label': 'Server Size',
                                     'type': 'select'}},
                    'services':
                    {'database':
                     {'component': {'interface': 'mysql',
                                    'type': 'database'},
                      'constraints': [{'count': 1}]}}},
                   'created': '2013-04-17 16:45:06 +0000',
                   'environment': {'description': 'This environment uses'
                                   'next-gen cloud servers.',
                                   'name': 'Next-Gen Open Cloud'},
                   'id': 'simulate',
                   'inputs': {'blueprint': {'region': 'ORD',
                                            'server_size': 1024,
                                            'url': 'http://jason.com/'}},
                   'status': 'NEW'}
        service_index = 1
        service_name = 'database'
        domain = 'checkmate.local'
        deployment = Deployment(content)
        output = deployment.create_resource_template(service_index,
                                                     definition,
                                                     service_name,
                                                     domain,
                                                     RequestContext())
        expected = {'component': 'mysql',
                    'dns-name': 'database.checkmate.local',
                    'instance': {},
                    'service': 'database',
                    'status': 'NEW',
                    'type': 'database'}
        self.assertEqual(output['dns-name'], expected['dns-name'])

if __name__ == '__main__':
    # Run tests. Handle our parameters separately
    import sys
    args = sys.argv[:]
    # Our --debug means --verbose for unitest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
