# pylint: disable=R0904,C0103
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
"""
Test coverage for mailgun provider module.
"""
import mock
import unittest

from checkmate import middleware
from checkmate.providers import base
from checkmate.providers.rackspace.mailgun import provider


class TestGenerateTemplate(unittest.TestCase):
    """Class for testing mailgun.generate_template."""

    def test_return_data(self):
        """Verifies return data from mailgun.generate_template."""
        prvdr = provider.Provider({})
        context = middleware.RequestContext()
        deployment = mock.Mock()
        deployment.get_setting.return_value = 'test.local'
        expected = [
            {
                'service': 'smtp',
                'provider': 'rackspace.mailgun',
                'dns-name': 'smtp.test.local',
                'instance': {},
                'desired-state': {},
                'type': 'mail-relay'
            }
        ]
        results = prvdr.generate_template(deployment, 'mail-relay', 'smtp',
                                          context, 1, prvdr.key, None)
        self.assertEqual(results, expected)


class TestGetCatalog(unittest.TestCase):
    """Class for testing mailgun get_catalog function."""

    @mock.patch.object(base.ProviderBase, 'get_catalog')
    def test_return_no_cache(self, mock_get_catalog):
        """Verifies template data returned."""
        mock_get_catalog.return_value = None
        prvdr = provider.Provider({})
        context = middleware.RequestContext()
        expected = {
            'mail-relay': {
                'relay_instance': {
                    'id': 'relay_instance',
                    'is': 'mail-relay',
                    'options': {},
                    'provides': [{'mail-relay': 'smtp'}]
                }
            }
        }
        results = prvdr.get_catalog(context)
        self.assertEqual(results, expected)

    @mock.patch.object(base.ProviderBase, 'get_catalog')
    def test_return_cache(self, mock_get_catalog):
        """Verifies template data returned."""
        expected = {
            'mail-relay': {
                'relay_instance': {
                    'id': 'relay_instance',
                    'is': 'mail-relay',
                    'options': {},
                    'provides': [{'mail-relay': 'smtp'}]
                }
            }
        }
        mock_get_catalog.return_value = expected
        prvdr = provider.Provider({})
        context = middleware.RequestContext()
        results = prvdr.get_catalog(context)
        self.assertEqual(results, expected)


class TestAddResourceTask(unittest.TestCase):
    """Class for testing mailgun add_resource_task function."""

    def setUp(self):
        """Setup vars for re-use."""
        self.context = middleware.RequestContext()
        self.resource = {'service': 'smtp', 'dns-name': 'test.local'}
        self.key = '1'
        self.deployment = {'id': '12345'}
        self.wf_spec = mock.Mock()

    @mock.patch.object(provider.utils, 'generate_password')
    @mock.patch.object(provider.specs, 'Celery')
    def test_task_gen(self, mock_wf_celery, mock_password):
        """Verifies method calls and results of add_resource_task."""
        prvdr = provider.Provider({})
        mock_create_domain = mock.Mock()
        mock_wf_celery.return_value = mock_create_domain
        mock_password.return_value = 'asdfg'
        expected = {
            'create': mock_create_domain,
            'final': mock_create_domain,
            'root': mock_create_domain
        }
        results = prvdr.add_resource_tasks(self.resource, self.key,
                                           self.wf_spec, self.deployment,
                                           self.context)
        self.assertEqual(expected, results)
        mock_wf_celery.assert_called_with(self.wf_spec,
            'Create Relay Domain 1 (smtp)',
            'checkmate.providers.rackspace.mailgun.tasks.create_domain',
            properties={'estimated_duration': 20},
            call_args=[{'username': None, 'domain': None, 'resource_key': '1',
                'auth_token': None, 'catalog': None, 'is_admin': False,
                'authenticated': False, 'tenant': None, 'read_only': False,
                'resource': None, 'show_deleted': False, 'roles': [],
                'region': None, 'user_tenants': None, 'base_url': None,
                'simulation': False, 'kwargs': {}, 'auth_source': None,
                'deployment_id': '12345'}, 'test.local', 'asdfg'],
            defines={'task_tags': ['create', 'root', 'final'], 'resource': '1',
                'provider': 'rackspace.mailgun'}
        )


class TestDeleteResourceTask(unittest.TestCase):
    """Class for testing mailgun delete_resource_task function."""

    def setUp(self):
        """Setup vars for re-use."""
        self.context = {}
        self.resource = {
            'service': 'smtp',
            'id': 'testing.local',
            'exists': False
        }
        self.key = '1'
        self.deployment_id = '12345'
        self.wf_spec = mock.Mock()

    @mock.patch.object(provider.specs, 'Celery')
    def test_task_gen(self, mock_wf_celery):
        """Verifies method calls and results of delete_resource_task."""
        prvdr = provider.Provider({})
        mock_delete_domain = mock.Mock()
        mock_wf_celery.return_value = mock_delete_domain
        expected = {
            'delete': mock_delete_domain,
            'final': mock_delete_domain,
            'root': mock_delete_domain
        }
        results = prvdr.delete_resource_tasks(self.wf_spec, self.context,
                                              self.deployment_id,
                                              self.resource, self.key)
        self.assertEqual(expected, results)
        mock_wf_celery.assert_called_with(self.wf_spec,
            'Delete Relay Domain 1 (smtp)',
            'checkmate.providers.rackspace.mailgun.tasks.delete_domain',
            properties={'estimated_duration': 20},
            call_args=[{'username': None, 'domain': None, 'resource_key': '1',
                'auth_token': None, 'catalog': None, 'is_admin': False,
                'authenticated': False, 'tenant': None, 'read_only': False,
                'resource': None, 'show_deleted': False, 'roles': [],
                'region': None, 'user_tenants': None, 'base_url': None,
                'simulation': False, 'kwargs': {}, 'auth_source': None,
                'deployment_id': '12345'}, 'testing.local', False],
            defines={'task_tags': ['delete', 'root', 'final'], 'resource': '1',
                'provider': 'rackspace.mailgun'}
        )


class TestGetResources(unittest.TestCase):
    """Class for testing mailgun get_resources."""

    @mock.patch.object(provider.Provider, 'connect')
    def test_success(self, mock_connect):
        """Verify list results from get_resources."""
        api = mock.Mock()
        expected = ['test', 'resources']
        api.list.return_value = expected
        mock_connect.return_value = api
        results = provider.Provider.get_resources({})
        self.assertEqual(results, expected)
        mock_connect.assert_called_with({})

    @mock.patch.object(provider.Provider, 'connect')
    def test_fail(self, mock_connect):
        """Verify empty list results from get_resources."""
        api = mock.Mock()
        expected = []
        api.list.return_value = None
        mock_connect.return_value = api
        results = provider.Provider.get_resources({})
        self.assertEqual(results, expected)
        mock_connect.assert_called_with({})
