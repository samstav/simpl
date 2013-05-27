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
