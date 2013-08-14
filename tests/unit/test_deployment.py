# pylint: disable=C0103,C0111,E1101,E1103,R0201,R0903,R0904,W0201,W0212,W0232
import mock
import unittest

import mox

from checkmate.deployment import (
    Deployment,
    LOG,
    update_deployment_status_new,
)
from checkmate.exceptions import (
    CheckmateBadState,
    CheckmateValidationException,
)
from checkmate import utils


class TestDeploymentStateTransitions(unittest.TestCase):
    def test_deployment_states_fail_to_plan(self):
        deployment = Deployment({'id': 'test'})
        self.assertEquals('NEW', deployment.fsm.current)

        deployment.fsm.change_to('FAILED')
        self.assertEquals('FAILED', deployment.fsm.current)

        deployment.fsm.change_to('DELETED')
        self.assertEquals('DELETED', deployment.fsm.current)

    def test_deployment_states_fail_to_build(self):
        deployment = Deployment({'id': 'test'})
        self.assertEquals('NEW', deployment.fsm.current)

        deployment.fsm.change_to('PLANNED')
        self.assertEquals('PLANNED', deployment.fsm.current)

        deployment.fsm.change_to('FAILED')
        self.assertEquals('FAILED', deployment.fsm.current)

    def test_deployment_states_build(self):
        deployment = Deployment({'id': 'test', 'status': 'PLANNED'})
        self.assertEquals('PLANNED', deployment.fsm.current)

        deployment.fsm.change_to('UP')
        self.assertEquals('UP', deployment.fsm.current)

    def test_deployment_states_alert_and_fix(self):
        deployment = Deployment({'id': 'test', 'status': 'UP'})
        self.assertEquals('UP', deployment.fsm.current)

        deployment.fsm.change_to('ALERT')
        self.assertEquals('ALERT', deployment.fsm.current)

        deployment.fsm.change_to('UP')
        self.assertEquals('UP', deployment.fsm.current)

    def test_deployment_states_reconnect(self):
        deployment = Deployment({'id': 'test', 'status': 'UP'})
        self.assertEquals('UP', deployment.fsm.current)

        deployment.fsm.change_to('UNREACHABLE')
        self.assertEquals('UNREACHABLE', deployment.fsm.current)

        deployment.fsm.change_to('UP')
        self.assertEquals('UP', deployment.fsm.current)

    def test_deployment_states_reconnect_to_alert(self):
        deployment = Deployment({'id': 'test', 'status': 'UNREACHABLE'})
        self.assertEquals('UNREACHABLE', deployment.fsm.current)

        deployment.fsm.change_to('ALERT')
        self.assertEquals(deployment.fsm.current, 'ALERT')

    def test_deployment_states_reconnect_to_down(self):
        deployment = Deployment({'id': 'test', 'status': 'UNREACHABLE'})
        self.assertEquals('UNREACHABLE', deployment.fsm.current)

        deployment.fsm.change_to('DOWN')
        self.assertEquals('DOWN', deployment.fsm.current)

    def test_deployment_states_up_down(self):
        deployment = Deployment({'id': 'test', 'status': 'UP'})
        self.assertEquals('UP', deployment.fsm.current)

        deployment.fsm.change_to('DOWN')
        self.assertEquals('DOWN', deployment.fsm.current)

        deployment.fsm.change_to('UP')
        self.assertEquals('UP', deployment.fsm.current)

    def test_deployment_states_delete_broken(self):
        deployment = Deployment({'id': 'test', 'status': 'DOWN'})
        self.assertEquals('DOWN', deployment.fsm.current)

        deployment.fsm.change_to('DELETED')
        self.assertEquals(deployment.fsm.current, 'DELETED')

    def test_deployment_states_delete(self):
        deployment = Deployment({'id': 'test', 'status': 'UP'})
        self.assertEquals('UP', deployment.fsm.current)

        deployment.fsm.change_to('DELETED')
        self.assertEquals('DELETED', deployment.fsm.current)

    @mock.patch.object(LOG, 'info')
    def test_deployment_status_logging(self, mock_logger):
        deployment = Deployment({'id': 'test', 'status': 'NEW', 'tenantId': 9})
        deployment['status'] = 'PLANNED'
        mock_logger.assert_called_with('Tenant: %s - Deployment %s going from '
                                       '%s to %s', 9, 'test', 'NEW', 'PLANNED')


class TestDeployments(unittest.TestCase):
    def setUp(self):
        deployment_dict = {
            'id': 'test',
            'name': 'test',
            'resources': {
                '0': {'provider': 'test'}
            },
            'status': 'NEW',
            'operation': {
                'status': 'NEW',
            },
        }
        self.deployment = Deployment(deployment_dict)
        self.mock = mox.Mox()
        self.deployment.environment = self.mock.CreateMockAnything()
        self.context = self.mock.CreateMockAnything()
        environment = self.mock.CreateMockAnything()
        self.provider = self.mock.CreateMockAnything()
        self.deployment.environment().AndReturn(environment)
        environment.get_provider('test').AndReturn(self.provider)

    def test_get_planned_resources(self):
        self.deployment["resources"] = {"1": {"status": "PLANNED",
                                              "provider": "load-balancer"},
                                        "2": {"status": "BUILD",
                                              "provider": "something"},
                                        "3": {"status": "NEW",
                                              "provider": "something else"}}
        resources = self.deployment.get_new_and_planned_resources()
        self.assertDictEqual(resources, {"1": {"status": "PLANNED",
                                               "provider": "load-balancer"},
                                         "3": {"status": "NEW",
                                               "provider": "something else"}})

    def test_get_indexed_resources(self):
        self.deployment["resources"] = {"1": {"status": "PLANNED",
                                              "provider": "load-balancer"},
                                        "2": {"status": "BUILD",
                                              "provider": "something"},
                                        "foo": {"status": "BUILD",
                                              "provider": "something"},
                                        "3": {"status": "BUILD",
                                              "provider": "something"},
                                        "bar": {"status": "NEW",
                                              "provider": "something else"}}
        resources = self.deployment.get_indexed_resources()
        self.assertDictEqual(resources, {"1": {"status": "PLANNED",
                                               "provider": "load-balancer"},
                                         "2": {"status": "BUILD",
                                               "provider": "something"},
                                         "3": {"status": "BUILD",
                                               "provider": "something"}})


    def test_get_workflow_id_when_w_id_not_in_operation(self):
        workflow_id = self.deployment.current_workflow_id()
        self.assertEqual(workflow_id, self.deployment['id'])

    def test_get_workflow_id_when_w_id_in_operation(self):
        self.deployment['operation']['workflow-id'] = "w_id"
        workflow_id = self.deployment.current_workflow_id()
        self.assertEqual(workflow_id, "w_id")

    def test_get_operation_for_workflow(self):
        self.deployment["operation"]["workflow-id"] = "w_id"
        expected_operation = {'operation': self.deployment["operation"]}
        self.assertEqual(self.deployment.get_operation("w_id"),
                         expected_operation)

    def test_get_operation_for_workflow_when_w_id_is_not_in_operation(self):
        expected_operation = {'operation': self.deployment["operation"]}
        self.assertEqual(self.deployment.get_operation("test"),
                         expected_operation)

    def test_get_operation_from_operation_histories(self):
        self.deployment["operations-history"] = [{'status': 'PAUSED',
                                                  'workflow-id': 'w_id'}]
        expected_operation = {'history': [self.deployment[
            "operations-history"][0]]}
        self.assertEqual(self.deployment.get_operation('w_id'),
                         expected_operation)

    def test_get_current_operation_for_workflow(self):
        self.deployment["operation"]["workflow-id"] = "w_id"
        expected_operation = self.deployment["operation"]
        self.assertEqual(self.deployment.get_current_operation("w_id"),
                         expected_operation)

    def test_get_current_operation_for_workflow_when_w_id_is_not_in_operation(
            self):
        expected_operation = self.deployment["operation"]
        self.assertEqual(self.deployment.get_current_operation("test"),
                         expected_operation)

    def test_get_current_operation_from_operation_histories(self):
        self.deployment["operations-history"] = [{'status': 'PAUSED',
                                                  'workflow-id': 'w_id'}]
        expected_operation = self.deployment["operations-history"][0]
        self.assertEqual(self.deployment.get_current_operation('w_id'),
                         expected_operation)

    def test_get_current_operation_for_w_id_not_associated_with_dep(self):
        self.deployment["operations-history"] = [
            {'status': 'PAUSED', 'workflow-id': 'w_id'}]
        self.assertIsNone(self.deployment.get_current_operation("foobar_w_id"))

    def test_get_operation_from_operation_histories_with_positional_elements(
            self):
        self.deployment["operations-history"] = [{'status': 'PAUSED',
                                                  'workflow-id': 'w_id'},
                                                 {'status': 'NEW',
                                                  'workflow-id': 'w_id2'}]
        expected_operation = {'history': [{}, self.deployment[
            "operations-history"][1]]}
        self.assertEqual(self.deployment.get_operation('w_id2'),
                         expected_operation)

    def test_get_operation_for_w_id_not_associated_with_deployment(self):
        self.deployment["operations-history"] = [
            {'status': 'PAUSED', 'workflow-id': 'w_id'}]
        self.assertIsNone(self.deployment.get_operation("foobar_w_id"))

    def test_get_statuses_for_deleted_resources(self):
        resource_status = {'instance:0': {'status': 'DELETED'}}
        self.provider.get_resource_status(self.context, 'test',
                                          {'provider': 'test'}, '0').\
            AndReturn(resource_status)
        self.context.__setitem__('resource', '0').AndReturn(None)
        self.mock.ReplayAll()

        expected = {
            'resources': resource_status,
            'deployment_status': 'DELETED',
            'operation_status': 'COMPLETE',
        }
        self.assertDictEqual(self.deployment.get_statuses(self.context),
                             expected)

    def test_get_statuses_for_active_resources(self):
        resource_status = {'instance:0': {'status': 'ACTIVE'}}
        self.provider.get_resource_status(self.context, 'test',
                                          {'provider': 'test'}, '0').\
            AndReturn(resource_status)
        self.context.__setitem__('resource', '0').AndReturn(None)
        self.mock.ReplayAll()

        expected = {
            'resources': resource_status,
            'deployment_status': 'UP',
            'operation_status': 'COMPLETE',
        }
        self.assertDictEqual(self.deployment.get_statuses(self.context),
                             expected)

    def test_get_statuses_for_new_resources(self):
        resource_status = {'instance:0': {'status': 'NEW'}}
        self.provider.get_resource_status(self.context, 'test',
                                          {'provider': 'test'}, '0').\
            AndReturn(resource_status)
        self.context.__setitem__('resource', '0').AndReturn(None)
        self.mock.ReplayAll()

        expected = {
            'resources': resource_status,
            'deployment_status': 'PLANNED',
            'operation_status': 'NEW',
        }
        self.assertDictEqual(self.deployment.get_statuses(self.context),
                             expected)

    def test_get_statuses_for_no_resources(self):
        self.provider.get_resource_status(self.context, 'test',
                                          {'provider': 'test'}, '0').\
            AndReturn({})
        self.context.__setitem__('resource', '0').AndReturn(None)
        self.mock.ReplayAll()

        expected = {
            'resources': {},
            'deployment_status': 'NEW',
            'operation_status': 'NEW',
        }
        self.assertDictEqual(self.deployment.get_statuses(self.context),
                             expected)

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
            'meta-data': {},
        }
        valid = Deployment(deployment)
        self.assertDictEqual(valid, deployment)

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
            self.assertIn(new_status, Deployment.FSM_TRANSITIONS)

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
        self.assertDictEqual(valid, deployment)


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
        self.assertEqual(results['Site Address']['extra-info'],
                         {'ipv4': 'a.b.c.d'})

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

    def test_on_postback_for_resource(self):
        """ Test on_postback dict merge and validation """
        deployment = Deployment({
            'id': 'test',
            'name': 'test',
            'inputs': {},
            'status': "UP",
        })
        updates = {
            'resources': {
                "0": {
                    'status': 'ACTIVE',
                    'status-message': ''
                }
            }
        }
        deployment.on_postback(updates)
        self.assertEqual("UP", deployment.get('status'))
        self.assertDictEqual(updates.get('resources'),
                             deployment.get('resources'))

    def test_on_postback_for_failed_deployment(self):
        deployment = Deployment({
            'id': 'test',
            'name': 'test',
            'inputs': {},
            'status': 'PLANNED',
        })
        updates = {'status': 'FAILED'}
        deployment.on_postback(updates)
        self.assertEqual("FAILED", deployment.get('status'))

    def test_on_postback_for_non_permitted_status_for_deployment(self):
        deployment = Deployment({
            'id': 'test',
            'name': 'test',
            'inputs': {},
            'status': 'UP',
        })
        updates = {'status': 'FAILED'}
        deployment.on_postback(updates)
        self.assertEqual("UP", deployment.get('status'))


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
