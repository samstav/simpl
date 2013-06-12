# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method
'''

import unittest2 as unittest

import mox

from checkmate.common import schema
from checkmate.deployment import (
    Deployment,
    update_deployment_status_new,
)
from checkmate.exceptions import (
    CheckmateBadState,
    CheckmateValidationException,
)
from checkmate import utils


class TestDeployments(unittest.TestCase):
    def test_schema(self):
        """Test the schema validates a deployment with all possible fields"""
        deployment = {
            'id': 'test',
            'name': 'test',
            'live': False,
            'operation': {},
            'operations-history': [],
            'created-by': 'me',
            'secrets': 'LOCKED',
            'plan': {},
            'inputs': {},
            'includes': {},
            'resources': {},
            'workflow': "abcdef",
            'status': "NEW",
            'created': "yesterday",
            'tenantId': "T1000",
            'blueprint': {
                'name': 'test bp',
                'meta-data': {
                    'schema-version': '0.7',
                }
            },
            'environment': {
                'name': 'environment',
                'providers': {},
            },
            'display-outputs': {},
        }
        valid = Deployment(deployment)
        self.assertDictEqual(valid._data, deployment)

    def test_schema_negative(self):
        """Test the schema validates a deployment with bad fields"""
        deployment = {
            'nope': None
        }
        self.assertRaises(CheckmateValidationException, Deployment, deployment)

    def test_status_changes(self):
        deployment = Deployment({
            'id': 'test',
            'name': 'test',
            'inputs': {},
            'includes': {},
            'resources': {},
            'workflow': "abcdef",
            'status': "NEW",
            'created': "yesterday",
            'tenantId': "T1000",
            'blueprint': {
                'name': 'test bp',
                'meta-data': {
                    'schema-version': '0.7'
                },
            },
            'environment': {
                'name': 'environment',
                'providers': {},
            },
            'display-outputs': {},
        })
        self.assertEqual(deployment['status'], 'NEW')
        self.assertEqual(deployment.fsm.current, 'NEW')
        deployment['status'] = 'PLANNED'
        self.assertEqual(deployment['status'], 'PLANNED')
        self.assertEqual(deployment.fsm.current, 'PLANNED')
        self.assertRaises(CheckmateBadState, deployment.__setitem__, 'status',
                          'DELETED')

    def test_invalid_status_rejected(self):
        self.assertRaises(CheckmateValidationException, Deployment, {'status':
                          'NOT VALID'})

    def test_convert_legacy_status(self):
        legacy_statuses = {
            "BUILD": 'UP',
            "CONFIGURE": 'UP',
            "ACTIVE": 'UP',
            'ERROR': 'FAILED',
            'DELETING': 'UP',
        }

        deployment = Deployment({
            'id': 'test',
            'name': 'test',
            'inputs': {},
            'status': "PLANNED",
        })
        self.assertEqual(deployment['status'], 'PLANNED')
        for legacy, new in legacy_statuses.iteritems():
            deployment.fsm.current = 'PLANNED'
            deployment['status'] = legacy
            self.assertEqual(deployment['status'], new)

    def test_edit_invalid_status_to_valid(self):
        deployment = Deployment({
            'id': 'test',
            'name': 'test',
            'inputs': {},
            'status': "CONFIGURE",  # legacy status
        })
        deployment['status'] = 'DELETED'  # valid, new status
        self.assertEqual(deployment['status'], 'DELETED')

    def test_legacy_to_new_maps_are_valid(self):
        '''Test the assumption thatlegacy_statuses maps to valid statuses'''
        for new_status in Deployment.legacy_statuses.values():
            self.assertIn(new_status, schema.DEPLOYMENT_STATUSES)

    def test_id_validation(self):
        self.assertRaises(CheckmateValidationException, Deployment,
            {'id': 1000})

    def test_schema_backwards_compatible(self):
        """Test the schema validates a an old deployment"""
        deployment = {
            'id': 'test',
            'name': 'test',
            # Following fields ommitted on pupose
            #'live': False,
            #'operation': {},
            #'operations-history': [],
            #'created-by': 'me',
            #'plan': {},
            #'inputs': {},
            #'includes': {},
            #'resources': {},
            'workflow': "abcdef",
            'status': "LAUNCHED",  # old status
            'blueprint': {
                'name': 'test bp',
                'options': {
                    'url': {
                        'regex': 'something',
                        'type': 'int',
                    },
                }
            },
            'environment': {
                'name': 'environment',
                'providers': {},
            },
        }
        valid = Deployment(deployment)
        deployment['status'] = 'UP'  # should be converted
        deployment['created'] = valid['created']  # gets added
        self.assertDictEqual(valid._data, deployment)


class TestGenerateServices(unittest.TestCase):

    def test_blank(self):
        deployment = Deployment({})
        services = deployment.calculate_services()
        self.assertDictEqual(services, {})

    def test_no_services(self):
        deployment = Deployment({'blueprint': {}})
        services = deployment.calculate_services()
        self.assertDictEqual(services, {})

    def test_blank_resources(self):
        deployment = Deployment({
            'blueprint': {
                'services': {
                    'app': {}
                }
            },
            'resources': {}
        })
        services = deployment.calculate_services()
        self.assertDictEqual(services, {'app': {'resources': []}})

    def test_simple(self):
        deployment = Deployment({
            'blueprint': {
                'services': {
                    'app': {
                        'component': {
                            'interface': 'http',
                            'name': 'wordpress',
                        }
                    }
                }
            }
        })
        services = deployment.calculate_services()
        expected = {
            'app': {
                'interfaces': {
                    'http': {}
                },
                'resources': [],
            }
        }
        self.assertDictEqual(services, expected)

    def test_one_resource(self):
        deployment = Deployment({
            'blueprint': {
                'services': {
                    'db': {
                        'component': {
                            'interface': 'mysql',
                            'name': 'database',
                        }
                    }
                }
            },
            'resources': {
                '0': {
                    'index': '0',
                    'service': 'db',
                    'instance': {
                        'interfaces': {
                            'mysql': {}
                        }
                    }
                }
            }
        })
        services = deployment.calculate_services()
        expected = {
            'db': {
                'interfaces': {
                    'mysql': {}
                },
                'resources': ['0'],
            }
        }
        self.assertDictEqual(services, expected)

    def test_host_resource(self):
        deployment = Deployment({
            'blueprint': {
                'services': {
                    'db': {
                        'component': {
                            'interface': 'mysql',
                            'name': 'database',
                        }
                    }
                }
            },
            'resources': {
                '0': {
                    'index': '0',
                    'service': 'db',
                    'instance': {
                        'interfaces': {
                            'mysql': {}
                        }
                    },
                    'hosted_on': '1',
                },
                '1': {
                    'index': '1',
                    'service': 'db',
                    'instance': {},
                    'hosts': ['0'],
                }
            }
        })
        services = deployment.calculate_services()
        expected = {
            'db': {
                'interfaces': {
                    'mysql': {}
                },
                'resources': ['0', '1'],
            }
        }
        services['db']['resources'].sort()
        self.assertDictEqual(services, expected)


class TestCalculateOutputs(unittest.TestCase):
    def setUp(self):
        self.deployment = Deployment(utils.yaml_to_dict("""
            blueprint:
              services:
                lb:
                  component:
                    interface: vip
                    type: load-balancer
                relations:
                  web: http
                web:
                  component:
                    type: application
                    interface: http
                db:
                  component:
                    interface: mysql
                    type: database
                  display-outputs:
                    "Database Password":
                      order: 2
                      source: interfaces/mysql/password
              options:
                simple:
                  type: integer
                  display-output: true  # show this as an display-output
                "Site Address":
                  type: url
              display-outputs:
                "Site Address":
                  type: url
                  source: options://url
                  extra-sources:
                    ipv4: "services://lb/interfaces/vip/ip"
                  order: 1
                  group: application
                "Private Key":
                  type: private-key
                  source: "resources://deployment-keys/instance/private_key"
                  order: 3
                  group: application
            inputs:
              blueprint:
                simple: 1
                url: http://localhost
            resources:
              '0':
                type: database
                service: db
                instance:
                  interfaces:
                    mysql:
                      password: MyPass
                hosted_on: '1'
              '1':
                type: compute
                hosts: ['0']
                service: db
              '2':
                type: load-balancer
                service: lb
                instance:
                  interfaces:
                    vip:
                      ip: a.b.c.d
              'deployment-keys':
                type: key-pair
                instance:
                  private_key: |
                    -----BEGIN RSA PRIVATE KEY---- ...
                  public_key: |
                    -----BEGIN PUBLIC KEY---- ...
    """))

    def test_calculate_outputs_none(self):
        '''Tests empty dict is returned if no display-outputs'''
        deployment = Deployment({
            'id': 'test',
            'name': 'test',
            'inputs': {},
            'status': "PLANNED",
        })
        results = deployment.calculate_outputs()
        self.assertEqual(results, {})

    def test_option(self):
        results = self.deployment.calculate_outputs()
        self.assertIn('simple', results)
        self.assertEqual(results['simple']['value'],
                         self.deployment['inputs']['blueprint']['simple'])
        self.assertEqual(results['simple']['type'],
                         self.deployment['blueprint']['options']['simple']
                         ['type'])

    def test_from_display_outputs(self):
        results = self.deployment.calculate_outputs()
        self.assertIn('Site Address', results)
        self.assertEqual(results['Site Address']['value'],
                         self.deployment['inputs']['blueprint']['url'])
        self.assertEqual(results['Site Address']['type'],
                         self.deployment['blueprint']['display-outputs']
                         ['Site Address']['type'])

    def test_from_service(self):
        results = self.deployment.calculate_outputs()
        self.assertIn('Database Password', results)
        self.assertEqual(results['Database Password']['value'],
                         self.deployment['resources']['0']['instance']
                         ['interfaces']['mysql']['password'])

    def test_extra_sources(self):
        results = self.deployment.calculate_outputs()
        print results

    def test_get_resource_value(self):
        results = self.deployment.calculate_outputs()
        self.assertIn('Private Key', results)
        self.assertTrue(results['Private Key']['value'].startswith(
                        '-----BEGIN RSA PRIVATE KEY----'))
        self.assertEqual(results['Private Key']['type'], 'private-key')


class TestCeleryTasks(unittest.TestCase):

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_update_deployment_status(self):
        """ Test deployment status update """
        expected = {'status': "DOWN"}
        db = self.mox.CreateMockAnything()
        db.save_deployment('1234', expected, partial=True).AndReturn(expected)
        self.mox.ReplayAll()
        update_deployment_status_new('1234', 'DOWN', driver=db)
        self.mox.VerifyAll()


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
