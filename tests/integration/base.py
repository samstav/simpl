# pylint: disable=C0103,C0302,E1101

# Copyright (c) 2011-2013 Rackspace Hosting
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

"""Base class for testing database drivers.

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
"""

import copy
import uuid

import abc

from checkmate import db
from checkmate import exceptions as cmexc
from checkmate import utils


class DBDriverTests(object):

    """Test Any Driver; mix in with unittest.TestCase."""

    __metaclass__ = abc.ABCMeta

    @abc.abstractproperty
    def connection_string(self):
        "For mocking a connection string."""
        return None  # meant to be overridden

    def setUp(self):
        if self.connection_string:
            self.driver = db.get_driver(
                connection_string=self.connection_string, reset=True)

    def test_driver_instantiation(self):
        self.assertEqual(self.driver.connection_string, self.connection_string)

    #
    # Tenants
    #
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
        self.assertEqual(2, len(tenants))
        self.assertIn("1234", tenants)
        self.assertIn("11111", tenants)
        # find just 'foo'
        tenants = self.driver.list_tenants('foo')
        self.assertIsNotNone(tenants)
        self.assertEqual(2, len(tenants))
        self.assertIn("1234", tenants)
        self.assertIn("11111", tenants)
        # find foo and bar
        tenants = self.driver.list_tenants('foo', 'bar')
        self.assertIsNotNone(tenants)
        self.assertEqual(1, len(tenants))
        self.assertIn("1234", tenants)
        # find just 'blap'
        tenants = self.driver.list_tenants('blap')
        self.assertIsNotNone(tenants)
        self.assertEqual(1, len(tenants))
        self.assertIn("11111", tenants)
        # find nothing
        tenants = self.driver.list_tenants('not there')
        self.assertIsNotNone(tenants)
        self.assertEqual(0, len(tenants))

    def test_save_tenant(self):
        # save a new one
        tenant_data = {"id": '1234', "tags": ['foo', 'bar']}
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
        self.assertRaises(
            cmexc.CheckmateException, self.driver.save_tenant, None)
        self.assertRaises(cmexc.CheckmateException, self.driver.save_tenant,
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

    #
    # Deployments
    #
    def test_save_get_deployment_with_defaults(self):
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234'}
        )
        self.assertEqual(
            {'id': '1234', 'tenantId': 'T3'},
            self.driver.get_deployment('1234')
        )

    def test_save_get_deployment_with_secrets(self):
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234'},
            secrets={'secret': 'SHHH!!!'}
        )
        self.assertEqual(
            {'id': '1234', 'tenantId': 'T3', 'secret': 'SHHH!!!'},
            self.driver.get_deployment('1234', with_secrets=True)
        )
        self.assertEqual(
            {'id': '1234', 'tenantId': 'T3'},
            self.driver.get_deployment('1234', with_secrets=False)
        )

    def test_save_deployment_with_merge(self):
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

        self.assertEqual(
            {'id': '1234', 'tenantId': 'T3', 'old': 'blarp', 'new': 'blerg'},
            self.driver.get_deployment('1234')
        )

    def test_save_deployment_with_overwrite(self):
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

        self.assertEqual(
            {'id': '1234', 'tenantId': 'T3', 'new': 'blerg'},
            self.driver.get_deployment('1234')
        )

    def test_get_deployments_found_nothing(self):
        self.assertEqual(
            {'_links': {}, 'results': {}, 'collection-count': 0},
            self.driver.get_deployments(tenant_id='T3')
        )

    def test_get_deployments_with_defaults(self):
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

        self.assertEqual(
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

        self.assertEqual(
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
        self.assertEqual(
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
        self.assertEqual(
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

        self.assertEqual(
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

        self.assertEqual(
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

        self.assertEqual(
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
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'status': 'NEW'}
        )

        self.assertEqual(
            {
                '_links': {},
                'results': {
                    '1234': {'id': '1234', 'tenantId': 'T3', 'status': 'NEW'}
                }
            },
            self.driver.get_deployments(tenant_id='T3', with_count=False)
        )

    def test_offset_passed_to_get_deployments_as_none(self):
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'status': 'NEW'}
        )

        self.assertEqual(
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
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'status': 'NEW'}
        )

        self.assertEqual(
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

        self.assertEqual(
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

        self.assertEqual(
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

        self.assertEqual(
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

        self.assertEqual(
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
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234', 'status': 'UP', 'r0': {'status': 'DELETED'}}
        )
        self.assertEqual(
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

    def test_partial_save_deployment_all_secrets(self):
        """Partial where all the keys are secret."""
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body={'id': '1234'},
            secrets={'secret': 'SHHH!!!'}
        )
        self.driver.save_deployment(
            '1234',
            tenant_id='T3',
            body=None,
            secrets={'secret': 'NEWWWW!!!'},
            partial=True,
        )

        self.assertEqual(
            {'id': '1234', 'tenantId': 'T3', 'secret': 'NEWWWW!!!'},
            self.driver.get_deployment('1234', with_secrets=True)
        )
        self.assertEqual(
            {'id': '1234', 'tenantId': 'T3'},
            self.driver.get_deployment('1234', with_secrets=False)
        )

    #
    #  Blueprints
    #
    #
    def test_get_blueprints_returns_all_blueprints(self):
        """DOCS."""
        self.driver.save_blueprint(
            '1234',
            body={'id': '1234'}
        )
        self.driver.save_blueprint(
            '4321',
            body={'id': '4321'}
        )
        self.driver.save_blueprint(
            '9999',
            body={'id': '9999'}
        )

        self.assertEqual(
            {
                '_links': {},
                'results': {
                    '1234': {'id': '1234'},
                    '4321': {'id': '4321'},
                    '9999': {'id': '9999'},
                },
                'collection-count': 3
            },
            self.driver.get_blueprints()
        )

    def test_get_blueprints_with_offset(self):
        """DOCS."""
        self.driver.save_blueprint(
            '1234',
            body={'id': '1234'}
        )
        self.driver.save_blueprint(
            '4321',
            body={'id': '4321'}
        )
        self.driver.save_blueprint(
            '9999',
            body={'id': '9999'}
        )

        self.assertEqual(
            {
                '_links': {},
                'results': {
                    '4321': {'id': '4321'},
                    '9999': {'id': '9999'},
                },
                'collection-count': 3
            },
            self.driver.get_blueprints(offset=1)
        )

    def test_get_blueprints_with_limit(self):
        """DOCS."""
        self.driver.save_blueprint(
            '1234',
            body={'id': '1234'}
        )
        self.driver.save_blueprint(
            '4321',
            body={'id': '4321'}
        )
        self.driver.save_blueprint(
            '9999',
            body={'id': '9999'}
        )

        self.assertEqual(
            {
                '_links': {},
                'results': {
                    '1234': {'id': '1234'},
                },
                'collection-count': 3
            },
            self.driver.get_blueprints(limit=1)
        )

    def test_get_blueprints_with_offset_and_limit(self):
        """DOCS."""
        self.driver.save_blueprint(
            '1234',
            body={'id': '1234'}
        )
        self.driver.save_blueprint(
            '4321',
            body={'id': '4321'}
        )
        self.driver.save_blueprint(
            '9999',
            body={'id': '9999'}
        )

        self.assertEqual(
            {
                '_links': {},
                'results': {
                    '4321': {'id': '4321'},
                },
                'collection-count': 3
            },
            self.driver.get_blueprints(offset=1, limit=1)
        )

    def test_offset_passed_to_get_blueprints_as_none(self):
        """DOCS."""
        self.driver.save_blueprint(
            '1234',
            body={'id': '1234'}
        )

        self.assertEqual(
            {
                '_links': {},
                'results': {
                    '1234': {'id': '1234'}
                },
                'collection-count': 1
            },
            self.driver.get_blueprints(offset=None)
        )

    def test_limit_passed_to_get_blueprints_as_none(self):
        """DOCS."""
        self.driver.save_blueprint(
            '1234',
            body={'id': '1234'}
        )

        self.assertEqual(
            {
                '_links': {},
                'results': {
                    '1234': {'id': '1234'}
                },
                'collection-count': 1
            },
            self.driver.get_blueprints(limit=None)
        )

    #
    # Workflows
    #
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


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
