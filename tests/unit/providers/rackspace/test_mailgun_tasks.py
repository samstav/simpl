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
Module for testing mailgun tasks.
"""
import mock
import unittest2 as unittest

import pyrax

from checkmate import exceptions
from checkmate import middleware
from checkmate.providers.rackspace.mailgun import tasks


class TestAddDomain(unittest.TestCase):
    """Class to test mailgun add_domain."""

    def setUp(self):
        self.domain_name = 'testing.local'
        self.password = 'testing_password'
        context = {
            'resource_key': '1',
            'deployment_id': '12345678-1234-5678-1234-567812345678'
        }
        self.context = middleware.RequestContext(**context)
        self.api = mock.MagicMock()

    @mock.patch.object(tasks.create_domain, 'callback')
    def test_sim(self, mock_callback):
        """Verifies method calls and results for create_domain simulation."""
        self.context.simulation = True
        expected = {
            'instance:1': {
                'exists': False,
                'id': 'testing.local',
                'interfaces': {
                    'smtp': {
                        'host': 'smtp.mailgun.org',
                        'port': 587,
                        'smtp_login': 'postmaster@testing.local',
                        'smtp_password': 'testing_password'
                    }
                },
                'name': 'testing.local',
                'status': 'ACTIVE'
            }
        }
        results = tasks.create_domain(self.context, self.domain_name,
                                      self.password, api=self.api)
        self.assertEqual(results, expected)
        mock_callback.assert_called_with(self.context, expected['instance:1'])

    @mock.patch.object(tasks.create_domain, 'callback')
    def test_no_name(self, mock_callback):
        """Verifies method calls and results for create_domain no name."""
        domain = mock.Mock()
        domain.id = 'rsd12345678.mailgun.org'
        domain.name = domain.id
        domain.smtp_login = 'postmaster@' + domain.name
        domain.smtp_password = self.password
        self.api.create.return_value = domain
        expected = {
            'instance:1': {
                'exists': False,
                'id': 'rsd12345678.mailgun.org',
                'interfaces': {
                    'smtp': {
                        'host': 'smtp.mailgun.org',
                        'port': 587,
                        'smtp_login': 'postmaster@rsd12345678.mailgun.org',
                        'smtp_password': 'testing_password'
                    }
                },
                'name': 'rsd12345678.mailgun.org',
                'status': 'ACTIVE'
            }
        }
        results = tasks.create_domain(self.context, None, self.password,
                                      api=self.api)
        self.assertEqual(results, expected)
        self.api.create.assert_called_with(domain.name,
                                           smtp_pass=self.password)
        mock_callback.assert_called_with(self.context, expected['instance:1'])

    @mock.patch.object(tasks.create_domain, 'callback')
    def test_not_unique(self, mock_callback):
        """Verifies method calls and results for create_domain not unique."""
        domain = mock.Mock()
        domain.id = self.domain_name
        domain.name = domain.id
        domain.smtp_login = 'postmaster@' + domain.name
        domain.smtp_password = self.password
        self.api.create.side_effect = pyrax.exceptions.DomainRecordNotUnique()
        self.api.get.return_value = domain
        expected = {
            'instance:1': {
                'exists': True,
                'id': 'testing.local',
                'interfaces': {
                    'smtp': {
                        'host': 'smtp.mailgun.org',
                        'port': 587,
                        'smtp_login': 'postmaster@testing.local',
                        'smtp_password': 'testing_password'
                    }
                },
                'name': 'testing.local',
                'status': 'ACTIVE'
            }
        }
        results = tasks.create_domain(self.context, self.domain_name,
                                      self.password, api=self.api)
        self.assertEqual(results, expected)
        self.api.get.assert_called_with(self.domain_name)
        mock_callback.assert_called_with(self.context, expected['instance:1'])

    def test_client_exception_400(self):
        """Verifies method calls and exception re-raised with ClientException
        code 400's.
        """
        self.api.create.side_effect = pyrax.exceptions.ClientException(
            code='400', message='Testing')
        self.assertRaisesRegexp(pyrax.exceptions.ClientException, 'Testing',
                                tasks.create_domain, self.context,
                                self.domain_name, self.password, api=self.api)

    def test_resumable_exc_raised(self):
        """Verifies a CheckmateResumableException is raised from a
        ClientException with a code not 400.
        """
        self.api.create.side_effect = pyrax.exceptions.ClientException(
            code='500', message='Testing')
        self.assertRaises(exceptions.CheckmateResumableException,
                          tasks.create_domain, self.context, self.domain_name,
                          self.password, api=self.api)

    def test_user_exc_raised(self):
        self.api.create.side_effect = StandardError('Testing')
        self.assertRaises(exceptions.CheckmateUserException,
                          tasks.create_domain, self.context, self.domain_name,
                          self.password, api=self.api)


class TestDeleteDomain(unittest.TestCase):
    """Class for testing the mailgun delete_domain function."""

    def setUp(self):
        """Assign vars for re-use."""
        self.domain_name = 'testing.local'
        context = {
            'resource_key': '1'
        }
        self.context = middleware.RequestContext(**context)
        self.api = mock.MagicMock()
        self.expected = {
            'instance:1': {
                'id': self.domain_name,
                'interfaces': {},
                'name': self.domain_name,
                'status': 'DELETED'
            }
        }

    @mock.patch.object(tasks.delete_domain, 'callback')
    def test_sim(self, mock_callback):
        """Verifies results on delete_domain with simulation."""
        self.context.simulation = True
        
        results = tasks.delete_domain(self.context, self.domain_name,
                                      api=self.api)
        self.assertEqual(results, self.expected)
        mock_callback.assert_called_with(self.context,
                                         self.expected['instance:1'])

    @mock.patch.object(tasks.delete_domain, 'callback')
    def test_success(self, mock_callback):
        """Verifies method calls and results in delete_domain."""
        
        results = tasks.delete_domain(self.context, self.domain_name,
                                      api=self.api)
        self.assertEqual(results, self.expected)
        self.api.delete.assert_called_with(self.domain_name)
        mock_callback.assert_called_with(self.context,
                                         self.expected['instance:1'])

    @mock.patch.object(tasks.delete_domain, 'callback')
    def test_domain_not_found(self, mock_callback):
        """Verifies results when domain not found on delete."""
        self.api.delete.side_effect = pyrax.exceptions.DomainRecordNotFound()
        results = tasks.delete_domain(self.context, self.domain_name,
                                      api=self.api)
        self.assertEqual(results, self.expected)

    def test_client_exception_400(self):
        """Verifies method calls and exception re-raised with ClientException
        code 400's.
        """
        self.api.delete.side_effect = pyrax.exceptions.ClientException(
            code='400', message='Testing')
        self.assertRaisesRegexp(pyrax.exceptions.ClientException, 'Testing',
                                tasks.delete_domain, self.context,
                                self.domain_name, api=self.api)

    def test_resumable_exc_raised(self):
        """Verifies a CheckmateResumableException is raised from a
        ClientException with a code not 400.
        """
        self.api.delete.side_effect = pyrax.exceptions.ClientException(
            code='500', message='Testing')
        self.assertRaises(exceptions.CheckmateResumableException,
                          tasks.delete_domain, self.context, self.domain_name,
                          api=self.api)

    def test_user_exc_raised(self):
        self.api.delete.side_effect = StandardError('Testing')
        self.assertRaises(exceptions.CheckmateUserException,
                          tasks.delete_domain, self.context, self.domain_name,
                          api=self.api)