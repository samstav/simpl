# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''

Base class for testing database drivers

This performs a full suite of tests on a driver to make sure it conforms to the
expected interface.

To use this:

from base import TestDBDriver

class TestMyDriver(TestDBDriver):
    connection_string = 'myDb://in-memory'  # or however your driver works

    def setUp(self):
        TestDBDriver.setUp(self)  # don't forget to call superclass

    def test_your_extra_tests(self):
        pass


'''
import copy
import uuid

from checkmate import db, utils
from abc import ABCMeta, abstractproperty
from checkmate.exceptions import CheckmateException


class DBDriverTests(object):
    '''Test Any Driver; mix in with unittest.TestCase '''

    __metaclass__ = ABCMeta

    @abstractproperty
    def connection_string(self):
        return None  # meant to be overridden

    def setUp(self):
        self.maxDiff = None
        if self.connection_string:
            self.driver = db.get_driver(
                connection_string=self.connection_string, reset=True)

    def test_instantiation(self):
        self.assertEqual(self.driver.connection_string, self.connection_string)

    def test_add_tags(self):
        new_tags = ['foo', 'bar', 'baz']
        self.driver.add_tenant_tags('1234', *new_tags)
        ten = self.driver.get_tenant('1234')
        self.assertIsNotNone(ten, 'Could not retrieve tenant after add tags')
        self.assertEqual(sorted(new_tags), sorted(ten.get('tags')),
                         'Tags not equal')
        new_tags.extend(["biff", "boo"])
        self.driver.add_tenant_tags('1234', 'biff', 'boo')
        ten = self.driver.get_tenant('1234')
        self.assertIsNotNone(ten, 'Could not retrieve tenant after add tags')
        self.assertEqual(
            sorted(new_tags),
            sorted(ten.get('tags')),
            'Tags not equal'
        )

    def test_list_tenants(self):
        self.driver.add_tenant_tags('1234', 'foo', 'bar', 'biff')
        self.driver.add_tenant_tags('11111', 'foo', 'blap')
        # find them all
        tenants = self.driver.list_tenants()
        self.assertIsNotNone(tenants)
        self.assertEquals(2, len(tenants))
        self.assertIn("1234", tenants)
        self.assertIn("11111", tenants)
        # find just 'foo'
        tenants = self.driver.list_tenants('foo')
        self.assertIsNotNone(tenants)
        self.assertEquals(2, len(tenants))
        self.assertIn("1234", tenants)
        self.assertIn("11111", tenants)
        # find foo and bar
        tenants = self.driver.list_tenants('foo', 'bar')
        self.assertIsNotNone(tenants)
        self.assertEquals(1, len(tenants))
        self.assertIn("1234", tenants)
        # find just 'blap'
        tenants = self.driver.list_tenants('blap')
        self.assertIsNotNone(tenants)
        self.assertEquals(1, len(tenants))
        self.assertIn("11111", tenants)
        # find nothing
        tenants = self.driver.list_tenants('not there')
        self.assertIsNotNone(tenants)
        self.assertEquals(0, len(tenants))

    def test_save_tenant(self):
        # save a new one
        tenant_data = {"tenant_id": '1234', "tags": ['foo', 'bar']}
        tenant = self.driver.get_tenant('1234')
        self.assertIsNone(tenant, "Tenant 1234 exists!")
        self.driver.save_tenant(tenant_data)
        tenant = self.driver.get_tenant('1234')
        self.assertIsNotNone(tenant)
        self.assertDictEqual(tenant_data, tenant)
        # amend the existing one
        tenant_data["tags"] = ['baz']
        self.driver.save_tenant(tenant_data)
        tenant = self.driver.get_tenant('1234')
        self.assertIsNotNone(tenant)
        self.assertDictEqual(tenant_data, tenant)
        # raises exception appropriately
        self.assertRaises(CheckmateException, self.driver.save_tenant, None)
        self.assertRaises(CheckmateException, self.driver.save_tenant,
                          {'tags': ['blap']})
        self.assertDictEqual(tenant_data, tenant)

    def test_update_secrets(self):
        _id = uuid.uuid4().hex[0:8]
        data = {
            "id": _id,
            "tenantId": "12345",
            "employee": {
                "name": "Bob",
                "title": "Mr.",
                "ssh_public_key": "rsa public key",
                "ssh_private_key": "a private key",
                "password": "password",
                "position": "left"
            },
            "server": {
                "access": {
                    "server_root_password": "password",
                    "server_privatekey": "private_key",
                    "server_public_key": "public_key"
                },
                "private_ip": "123.45.67.89",
                "public_ip": "127.0.0.1",
                "host_name": "server1"
            },
            "safe_val": "hithere",
            "secret_value": "Immasecret"
        }

        safe = {
            "id": _id,
            "tenantId": "12345",
            "employee": {
                "name": "Bob",
                "title": "Mr.",
                "ssh_public_key": "rsa public key",
                "position": "left"
            },
            "server": {
                "access": {
                    "server_public_key": "public_key"
                },
                "private_ip": "123.45.67.89",
                "public_ip": "127.0.0.1",
                "host_name": "server1"
            },
            "safe_val": "hithere",
            "secret_value": "Immasecret"
        }

        secret = {
            "employee": {
                "ssh_private_key": "a private key",
                "password": "password",
            },
            "server": {
                "access": {
                    "server_root_password": "password",
                    "server_privatekey": "private_key",
                }
            }
        }
        original = copy.deepcopy(data)
        body, secrets = utils.extract_sensitive_data(data)
        self.assertDictEqual(safe, body)
        self.assertDictEqual(secret, secrets)
        results = self.driver.save_deployment(_id, body, secrets=secrets)
        self.assertDictEqual(results, body)
        # retrieve the deployment with secrets to make sure we get them
        # correctly
        results = self.driver.get_deployment(_id, with_secrets=True)
        self.assertDictEqual(original, results)
        # use the "safe" version and add a new secret
        results = self.driver.save_deployment(_id, safe,
                                              secrets={
                                                  "global_password":
                                                  "password secret"
                                              })
        self.assertDictEqual(safe, results)
        # update the copy with the new secret
        original['global_password'] = "password secret"
        # retrieve with secrets and make sure it was updated correctly
        results = self.driver.get_deployment(_id, with_secrets=True)
        self.assertDictEqual(original, results)

    def test_workflows(self):
        _id = uuid.uuid4().hex[0:8]
        entity = {
            u'id': _id,
            u'name': u'My Workflow',
            u'credentials': [u'My Secrets']
        }
        body, secrets = utils.extract_sensitive_data(entity)
        results = self.driver.save_workflow(entity['id'], body, secrets,
                                            tenant_id='T1000')
        self.assertDictEqual(results, body)

        results = self.driver.get_workflow(entity['id'], with_secrets=True)
        entity['tenantId'] = u'T1000'  # gets added
        self.assertDictEqual(results, entity)
        self.assertIn('credentials', results)

        body[u'name'] = u'My Updated Workflow'
        entity[u'name'] = u'My Updated Workflow'
        results = self.driver.save_workflow(entity[u'id'], body)

        results = self.driver.get_workflow(entity[u'id'], with_secrets=True)
        self.assertIn(u'credentials', results)
        self.assertDictEqual(results, entity)

        results = self.driver.get_workflow(entity[u'id'], with_secrets=False)
        self.assertNotIn(u'credentials', results)
        body[u'tenantId'] = u'T1000'  # gets added
        self.assertDictEqual(results, body)

    def test_workflow_locking(self):
        _id = uuid.uuid4().hex[0:8]
        entity = {
            'id': _id,
            'name': 'My Workflow'
        }
        results = self.driver.save_workflow(entity['id'], entity, None,
                                            tenant_id='T1000')

        _, key = self.driver.lock_workflow(entity['id'])
        with self.assertRaises(db.ObjectLockedError):
            self.driver.lock_workflow(entity['id'])

        entity['name'] = 'My Updated Workflow'
        results = self.driver.save_workflow(entity['id'], entity)
        self.assertEqual(entity, results)

        #  Check still locked
        with self.assertRaises(db.ObjectLockedError):
            self.driver.lock_workflow(entity['id'])

        self.driver.unlock_workflow(entity['id'], key=key)
        self.driver.lock_workflow(entity['id'])  # should succeed


    def test_save_get_deployment_with_defaults(self):
        '''We are really testing deployment, but using deployment so that the
        test works regardless of driver implementation
        '''
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234'}
        )
        self.assertEquals(
            {'id': '1234', 'tenantId': 'T3'},
            self.driver.get_deployment('1234')
        )

    def test_save_get_deployment_with_secrets(self):
        '''We are really testing deployment, but using deployment so that the
        test works regardless of driver implementation
        '''
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234'},
            secrets={'secret': 'SHHH!!!'}
        )
        self.assertEquals(
            {'id': '1234', 'tenantId': 'T3', 'secret': 'SHHH!!!'},
            self.driver.get_deployment('1234', with_secrets=True)
        )
        self.assertEquals(
            {'id': '1234', 'tenantId': 'T3'},
            self.driver.get_deployment('1234', with_secrets=False)
        )

    def test_save_deployment_with_merge(self):
        '''We are really testing deployment, but using deployment so that the
        test works regardless of driver implementation
        '''
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'old': 'blarp'}
        )

        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'new': 'blerg'},
            partial=True  # merge_existing in _save_deployment
        )

        self.assertEquals(
            {'id': '1234', 'tenantId': 'T3', 'old': 'blarp', 'new': 'blerg'},
            self.driver.get_deployment('1234')
        )

    def test_save_deployment_with_overwrite(self):
        '''We are really testing deployment, but using deployment so that the
        test works regardless of driver implementation
        '''
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'old': 'blarp'}
        )

        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'new': 'blerg'},
            partial=False  # merge_existing in _save_deployment
        )

        self.assertEquals(
            {'id': '1234', 'tenantId': 'T3', 'new': 'blerg'},
            self.driver.get_deployment('1234')
        )

    def test_get_deployments_found_nothing(self):
        '''We are really testing deployment, but using deployment so that the
        test works regardless of driver implementation
        '''
        self.assertEquals(
            {'_links': {}, 'results': {}, 'collection-count': 0},
            self.driver.get_deployments(tenant_id='T3')
        )

    def test_get_deployments_with_defaults(self):
        '''We are really testing deployment, but using deployment so that the
        test works regardless of driver implementation
        '''
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'status': 'NEW'}
        )
        self.driver.save_deployment(
            '4321',
            tenant_id='T3',
            body={'id': '4321', 'status': 'NEW'}
        )
        self.driver.save_deployment(
            '9999',
            tenant_id='TOTHER',
            body={'id': '9999', 'status': 'NEW'}
        )

        self.assertEquals(
            {
                '_links': {},
                'results': {
                    '1234': {'id': '1234', 'tenantId': 'T3', 'status': 'NEW'},
                    '4321': {'id': '4321', 'tenantId': 'T3', 'status': 'NEW'}
                },
                'collection-count': 2
            },
            self.driver.get_deployments(tenant_id='T3')
        )

    def test_get_deployments_with_no_tenant_id_returns_all_deployments(self):
        '''We are really testing deployment, but using deployment so that the
        test works regardless of driver implementation
        '''
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'status': 'NEW'}
        )
        self.driver.save_deployment(
            '4321',
            tenant_id='T3',
            body={'id': '4321', 'status': 'NEW'}
        )
        self.driver.save_deployment(
            '9999',
            tenant_id='TOTHER',
            body={'id': '9999', 'status': 'NEW'}
        )

        self.assertEquals(
            {
                '_links': {},
                'results': {
                    '1234': {'id': '1234', 'tenantId': 'T3', 'status': 'NEW'},
                    '4321': {'id': '4321', 'tenantId': 'T3', 'status': 'NEW'},
                    '9999': {
                        'id': '9999',
                        'tenantId': 'TOTHER',
                        'status': 'NEW',
                    }
                },
                'collection-count': 3
            },
            self.driver.get_deployments(tenant_id=None)
        )

    def test_get_deployments_with_secrets(self):
        '''We are really testing deployment, but using deployment so that the
        test works regardless of driver implementation
        '''
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'status': 'NEW'},
            secrets={'secret': 'SHHH!!!'}
        )
        self.driver.save_deployment(
            '4321',
            tenant_id='T3',
            body={'id': '4321', 'status': 'NEW'}
        )
        self.assertEquals(
            {
                '_links': {},
                'results': {
                    '1234': {
                        'id': '1234',
                        'tenantId': 'T3',
                        'secret': 'SHHH!!!',
                        'status': 'NEW'
                    },
                    '4321': {
                        'id': '4321',
                        'tenantId': 'T3',
                        'status': 'NEW'
                    }
                },
                'collection-count': 2
            },
            self.driver.get_deployments(tenant_id='T3', with_secrets=True)
        )
        self.assertEquals(
            {
                '_links': {},
                'results': {
                    '1234': {'id': '1234', 'tenantId': 'T3', 'status': 'NEW'},
                    '4321': {'id': '4321', 'tenantId': 'T3', 'status': 'NEW'}
                },
                'collection-count': 2
            },
            self.driver.get_deployments(tenant_id='T3', with_secrets=False)
        )

    def test_get_deployments_with_offset(self):
        '''We are really testing deployment, but using deployment so that the
        test works regardless of driver implementation
        '''
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'status': 'NEW'}
        )
        self.driver.save_deployment(
            '4321',
            tenant_id='T3',
            body={'id': '4321', 'status': 'NEW'}
        )

        self.assertEquals(
            {
                '_links': {},
                'results': {
                    '4321': {'id': '4321', 'tenantId': 'T3', 'status': 'NEW'}
                },
                'collection-count': 2
            },
            self.driver.get_deployments(tenant_id='T3', offset=1)
        )

    def test_get_deployments_with_limit(self):
        '''We are really testing deployment, but using deployment so that the
        test works regardless of driver implementation
        '''
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'status': 'NEW', 'created': '2011-01-01'}
        )
        self.driver.save_deployment(
            '4321',
            tenant_id='T3',
            body={'id': '4321', 'status': 'NEW', 'created': '2012-01-01'}
        )

        self.assertEquals(
            {
                '_links': {},
                'results': {
                    '4321': {
                        'id': '4321',
                        'tenantId': 'T3',
                        'status': 'NEW',
                        'created': '2012-01-01',
                    }
                },
                'collection-count': 2
            },
            self.driver.get_deployments(tenant_id='T3', limit=1)
        )

    def test_get_deployments_with_offset_and_limit(self):
        '''We are really testing deployment, but using deployment so that the
        test works regardless of driver implementation
        '''
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'status': 'NEW', 'created': '2011-01-01'}
        )
        self.driver.save_deployment(
            '4321',
            tenant_id='T3',
            body={'id': '4321', 'status': 'NEW', 'created': '2012-01-01'}
        )
        self.driver.save_deployment(
            '5678',
            tenant_id='T3',
            body={'id': '5678', 'status': 'NEW', 'created': '2013-01-01'}
        )

        self.assertEquals(
            {
                '_links': {},
                'results': {
                    '4321': {
                        'id': '4321',
                        'tenantId': 'T3',
                        'status': 'NEW',
                        'created': '2012-01-01',
                    },
                    '1234': {
                        'id': '1234',
                        'tenantId': 'T3',
                        'status': 'NEW',
                        'created': '2011-01-01',
                    }
                },
                'collection-count': 3
            },
            self.driver.get_deployments(tenant_id='T3', offset=1, limit=2)
        )

    def test_get_deployments_omitting_count(self):
        '''We are really testing deployment, but using deployment so that the
        test works regardless of driver implementation
        '''
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'status': 'NEW'}
        )

        self.assertEquals(
            {
                '_links': {},
                'results': {
                    '1234': {'id': '1234', 'tenantId': 'T3', 'status': 'NEW'}
                }
            },
            self.driver.get_deployments(tenant_id='T3', with_count=False)
        )

    def test_offset_passed_to_get_deployments_as_none(self):
        '''We are really testing deployment, but using deployment so that the
        test works regardless of driver implementation
        '''
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'status': 'NEW'}
        )

        self.assertEquals(
            {
                '_links': {},
                'results': {
                    '1234': {'id': '1234', 'tenantId': 'T3', 'status': 'NEW'}
                },
                'collection-count': 1
            },
            self.driver.get_deployments(tenant_id='T3', offset=None)
        )

    def test_limit_passed_to_get_deployments_as_none(self):
        '''We are really testing deployment, but using deployment so that the
        test works regardless of driver implementation
        '''
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'status': 'NEW'}
        )

        self.assertEquals(
            {
                '_links': {},
                'results': {
                    '1234': {'id': '1234', 'tenantId': 'T3', 'status': 'NEW'}
                },
                'collection-count': 1
            },
            self.driver.get_deployments(tenant_id='T3', limit=None)
        )

    def test_get_deployments_deleted_omitted_by_default(self):
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'status': 'PLANNED'}
        )
        self.driver.save_deployment(
            '4321',
            tenant_id='T3',
            body={'id': '4321', 'status': 'DELETED'}
        )

        self.assertEquals(
            {
                '_links': {},
                'results': {
                    '1234': {
                        'id': '1234',
                        'tenantId': 'T3',
                        'status': 'PLANNED'
                    }
                },
                'collection-count': 1
            },
            self.driver.get_deployments(tenant_id='T3')
        )

    def test_get_deployments_omitting_deleted(self):
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'status': 'PLANNED'}
        )
        self.driver.save_deployment(
            '4321',
            tenant_id='T3',
            body={'id': '4321', 'status': 'DELETED'}
        )

        self.assertEquals(
            {
                '_links': {},
                'results': {
                    '1234': {
                        'id': '1234',
                        'tenantId': 'T3',
                        'status': 'PLANNED'
                    }
                },
                'collection-count': 1
            },
            self.driver.get_deployments(tenant_id='T3', with_deleted=False)
        )

    def test_get_deployments_including_deleted(self):
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'status': 'PLANNED'}
        )
        self.driver.save_deployment(
            '4321',
            tenant_id='T3',
            body={'id': '4321', 'status': 'DELETED'}
        )

        self.assertEquals(
            {
                '_links': {},
                'results': {
                    '1234': {
                        'id': '1234',
                        'tenantId': 'T3',
                        'status': 'PLANNED'
                    },
                    '4321': {
                        'id': '4321',
                        'tenantId': 'T3',
                        'status': 'DELETED'
                    }
                },
                'collection-count': 2
            },
            self.driver.get_deployments(tenant_id='T3', with_deleted=True)
        )

    def test_get_deployments_with_limit_offset_and_omitting_deleted(self):
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'status': 'PLANNED', 'created': '2010-01-01'}
        )
        self.driver.save_deployment(
            '9999',
            tenant_id='T3',
            body={
                'id': '9999',
                'status': 'UP',
                'r0': {'status': 'DELETED'},
                'created': '2011-01-01',
            }
        )
        self.driver.save_deployment(
            '4321',
            tenant_id='T3',
            body={'id': '4321', 'status': 'FAILED', 'created': '2012-01-01'}
        )
        self.driver.save_deployment(
            '5678',
            tenant_id='T3',
            body={'id': '5678', 'status': 'NEW', 'created': '2013-01-01'}
        )
        self.driver.save_deployment(
            '8765',
            tenant_id='T3',
            body={'id': '8765', 'status': 'ALERT', 'created': '2014-01-01'}
        )
        self.driver.save_deployment(
            '0000',
            tenant_id='T3',
            body={'id': '0000', 'status': 'DELETED', 'created': '2015-01-01'}
        )

        self.assertEquals(
            {
                '_links': {},
                'results': {
                    '4321': {
                        'status': 'FAILED',
                        'created': '2012-01-01',
                        'id': '4321',
                        'tenantId': 'T3',
                    },
                    '9999': {
                        'status': 'UP',
                        'tenantId': 'T3',
                        'r0': {'status': 'DELETED'},
                        'id': '9999',
                        'created': '2011-01-01',
                    },
                    '1234': {
                        'status': 'PLANNED',
                        'created': '2010-01-01',
                        'id': '1234',
                        'tenantId': 'T3',
                    }
                },
                'collection-count': 5,
            },
            self.driver.get_deployments(
                tenant_id='T3',
                offset=2,
                limit=3,
                with_deleted=False
            )
        )

    def test_get_deployments_with_deleted_resource(self):
        '''Make sure we still get a deployment when it is not DELETED,
        but one of its Resources IS DELETED
        '''
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'status': 'UP', 'r0': {'status': 'DELETED'}}
        )
        self.assertEquals(
            {
                '_links': {},
                'results': {
                    '1234': {
                        'id': '1234',
                        'tenantId': 'T3',
                        'status': 'UP',
                        'r0': {'status': 'DELETED'},
                    }
                },
                'collection-count': 1
            },
            self.driver.get_deployments(tenant_id='T3', with_deleted=False)
        )

    def test_convert_invalid_deployment_status(self):
        '''We want to make sure that old statuses (ex. LAUNCHED) get converted
        before they are returned back to the engine
        '''
        self.driver.save_deployment(
            '1',
            tenant_id='T3',
            body={'id': '1', 'status': 'LAUNCHED'}
        )
        self.driver.save_deployment(
            '2',
            tenant_id='T3',
            body={'id': '2', 'status': 'ERROR'}
        )
        self.driver.save_deployment(
            '3',
            tenant_id='T3',
            body={'id': '3', 'status': 'DELETING'}
        )
        self.driver.save_deployment(
            '4',
            tenant_id='T3',
            body={'id': '4', 'status': 'BUILD'}
        )
        self.driver.save_deployment(
            '5',
            tenant_id='T3',
            body={'id': '5', 'status': 'ACTIVE'}
        )
        self.driver.save_deployment(
            '6',
            tenant_id='T3',
            body={'id': '6', 'status': 'CONFIGURE'}
        )

        results = self.driver.get_deployments(tenant_id='T3')
        self.assertEquals(results['results']['1']['status'], 'UP')
        self.assertEquals(results['results']['2']['status'], 'FAILED')
        self.assertEquals(results['results']['3']['status'], 'UP')
        self.assertEquals(results['results']['4']['status'], 'UP')
        self.assertEquals(results['results']['5']['status'], 'UP')
        self.assertEquals(results['results']['6']['status'], 'UP')

    def test_trim_get_deployments(self):
        '''Make sure we don't return too much data in list deployments'''
        self.driver.save_deployment(
            '1',
            tenant_id='T3',
            body={
                'id': '1',
                'status': 'LAUNCHED',
                'blueprint': {
                    'documentation': {},
                    'options': {},
                    'services': {},
                    'resources': {},
                },
                'environment': {
                    'providers': {},
                },
                'inputs': {},
                'plan': {},
                'display-outputs': {},
                'resources': {},
            }
        )
        results = self.driver.get_deployments(tenant_id='T3', with_count=True)
        self.assertEqual(results['collection-count'], 1)
        expected = {
            u'id': u'1',
            u'tenantId': u'T3',
            u'status': 'UP',
            u'blueprint': {},
            u'environment': {},
        }
        self.assertDictEqual(expected, results['results']['1'])

    def test_trim_get_workflows(self):
        '''Make sure we don't return too much data in list workflows'''
        self.driver.save_workflow(
            '1',
            tenant_id='T3',
            body={
                'id': '1',
                'name': {},
                'progress': {},
                'status': 'running',
                'wf_spec': {
                    'specs': [],
                },
                'task_tree': {},
                'tenantId': "T3",
            }
        )
        results = self.driver.get_workflows(tenant_id='T3')
        self.assertEqual(results['collection-count'], 1),
        expected = {
            u'id': u'1',
            u'name': {},
            u'progress': {},
            u'status': u'running',
            u'wf_spec': {},
            u'tenantId': u"T3",
        }
        self.assertDictEqual(expected, results['results']['1'])


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
