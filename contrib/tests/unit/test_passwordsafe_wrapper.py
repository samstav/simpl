# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import unittest

import responses
from requests.exceptions import HTTPError
from contrib import bootstrap


class TestPasswordSafe(unittest.TestCase):
    def setUp(self):
        self.auth_token = 'test_token'
        self.project_name = 'test_project'
        self.passwordsafe_url = 'https://test.local'
        self.env_vars = ['TEST', 'TEST2']
        self.secrets = {'TEST': 'test', 'TEST2': 'test'}
        self._project_id = '123456'
        self._projects_url = '%s/projects' % self.passwordsafe_url
        self._project_response = '[{"project": {"id": %s, "name": "%s"}}]' % (
            self._project_id, self.project_name)
        self._credentials_response = '[{"credential": {"id": 1111, "prerequisites": "TEST", "password": "test"}}, {"credential": {"id": 2222, "prerequisites": "TEST2", "password": "test"}}]'
        self._credentials_url = '%s/projects/%s/credentials' % (
            self.passwordsafe_url, self._project_id)

    @responses.activate
    def test_positive(self):
        responses.add(responses.GET,
                      self._projects_url,
                      body=self._project_response,
                      content_type="application/json"
                      )
        responses.add(responses.GET,
                      self._credentials_url,
                      body=self._credentials_response,
                      content_type="application/json"
                      )
        wrapper = bootstrap.PasswordSafeWrapper(self.passwordsafe_url,
                                                self.project_name,
                                                self.auth_token,
                                                self.env_vars)
        self.assertEqual(self.secrets, wrapper.secrets)

    @responses.activate
    def test_no_project_found(self):
        responses.add(responses.GET,
                      self._projects_url,
                      body='[]',
                      content_type="application/json"
                      )
        self.assertRaises(LookupError, bootstrap.PasswordSafeWrapper,
                          self.passwordsafe_url,
                          'non-existent-project',
                          self.auth_token,
                          self.env_vars)

    @responses.activate
    def test_credentials_403(self):
        responses.add(responses.GET,
                      self._projects_url,
                      body=self._project_response,
                      content_type="application/json",
                      )
        responses.add(responses.GET,
                      self._credentials_url,
                      body=self._credentials_response,
                      content_type="application/json",
                      status=403
                      )
        self.assertRaises(HTTPError, bootstrap.PasswordSafeWrapper,
                          self.passwordsafe_url,
                          self.project_name,
                          self.auth_token,
                          self.env_vars)

    @responses.activate
    def test_projects_403(self):
        responses.add(responses.GET,
                      self._projects_url,
                      body=self._project_response,
                      content_type="application/json",
                      status=403
                      )
        self.assertRaises(HTTPError, bootstrap.PasswordSafeWrapper,
                          self.passwordsafe_url,
                          self.project_name,
                          self.auth_token,
                          self.env_vars)

    @responses.activate
    def test_missing_credential(self):
        responses.add(responses.GET,
                      self._projects_url,
                      body=self._project_response,
                      content_type="application/json"
                      )
        responses.add(responses.GET,
                      self._credentials_url,
                      body=self._credentials_response,
                      content_type="application/json"
                      )

        self.assertRaises(LookupError, bootstrap.PasswordSafeWrapper,
                          self.passwordsafe_url,
                          self.project_name,
                          self.auth_token,
                          self.env_vars + ["TEST3"])

    @responses.activate
    def test_multiple_matching_credentials(self):
        responses.add(responses.GET,
                      self._projects_url,
                      body=self._project_response,
                      content_type="application/json"
                      )
        responses.add(responses.GET,
                      self._credentials_url,
                      body='[{"credential": {"id": 1111, "prerequisites": "TEST", "password": "test"}}, {"credential": {"id": 2222, "prerequisites": "TEST", "password": "test2"}}]',
                      content_type="application/json"
                      )

        self.assertRaises(LookupError, bootstrap.PasswordSafeWrapper,
                          self.passwordsafe_url,
                          self.project_name,
                          self.auth_token,
                          self.env_vars)