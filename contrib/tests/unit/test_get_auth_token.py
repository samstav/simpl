# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock
import unittest

from contrib import bootstrap


class TestGetAuthToken(unittest.TestCase):

    def setUp(self):
        self.username = 'test_username'
        self.identity_url = 'https://url.test'
        self.password = 'test_password'
        self.rsa_token = 'test_token'
        self.apikey = 'test_apikey'
        self._expected = '123456'

    @mock.patch('requests.post')
    def test_expected_auth(self, mock_post):
        mock_post.return_value.json.return_value = {
            'access': {'token': {'id': self._expected}}}

        self.assertEqual(self._expected,
                         bootstrap.get_auth_token(
                             self.identity_url,
                             sso_username=self.username,
                             token_key=self.rsa_token))

    @mock.patch('contrib.bootstrap._prompt_for_username')
    @mock.patch('requests.post')
    def test_missing_user(self, mock_post, mock_username_prompt):
        mock_post.return_value.json.return_value = {
            'access': {'token': {'id': self._expected}}}
        mock_username_prompt.return_value = 'mock_user'

        self.assertEqual(self._expected,
                         bootstrap.get_auth_token(
                             self.identity_url,
                             sso_username=None,
                             token_key=self.rsa_token))

    @mock.patch('contrib.bootstrap._prompt_for_token')
    @mock.patch('requests.post')
    def test_missing_token(self, mock_post, mock_token_prompt):
        mock_post.return_value.json.return_value = {
            'access': {'token': {'id': self._expected}}}
        mock_token_prompt.return_value = 'mock_token'

        self.assertEqual(self._expected,
                         bootstrap.get_auth_token(
                             self.identity_url,
                             sso_username=self.username))

    def test_fails_missing_if_silent(self):
        self.assertRaises(TypeError, bootstrap.get_auth_token,
                          self.identity_url, silent=True)


class TestAuthToken(unittest.TestCase):

    def setUp(self):
        self.username = 'test_username'
        self.identity_url = 'https://url.test'
        self.password = 'test_password'
        self.rsa_token = 'test_token'
        self.apikey = 'test_apikey'

    def test_no_credential(self):
        self.assertRaises(TypeError, bootstrap._get_auth_token,
                          self.identity_url, self.username)

    @mock.patch('requests.post')
    def test_unauthorized(self, mock_post):
        mock_post.return_value.json.return_value = {
            'unauthorized': {'message': 'get out', 'code': 401}}

        self.assertRaises(bootstrap.UnauthorizedException,
                          bootstrap._get_auth_token,
                          self.identity_url,
                          self.username,
                          rsa_token=self.rsa_token)

    @mock.patch('requests.post')
    def test_bad_request(self, mock_post):
        mock_post.return_value.json.return_value = {
            'badRequest': {'message': 'this is bad', 'code': 400}}

        self.assertRaises(bootstrap.UnauthorizedException,
                          bootstrap._get_auth_token,
                          self.identity_url,
                          self.username,
                          rsa_token=self.rsa_token)

    @mock.patch('requests.post')
    def test_unexpected_response(self, mock_post):
        mock_post.return_value.json.return_value = {
            'unexpected': {'some_random_key': 'WAT'}}

        self.assertRaises(bootstrap.UnexpectedResponse,
                          bootstrap._get_auth_token,
                          self.identity_url,
                          self.username,
                          rsa_token=self.rsa_token)

    @mock.patch('requests.post')
    def test_expected_response(self, mock_post):
        expected = '123456'
        mock_post.return_value.json.return_value = {
            'access': {'token': {'id': expected}}}

        self.assertEqual(expected,
                         bootstrap._get_auth_token(
                             self.identity_url,
                             self.username,
                             rsa_token=self.rsa_token))


class TestAuthPayload(unittest.TestCase):
    def setUp(self):
        self.username = 'test_username'
        self.password = 'test_password'
        self.rsa_token = 'test_token'
        self.apikey = 'test_apikey'

    def test_auth_with_rsa_token(self):
        wanted = {'auth': {'RAX-AUTH:domain': {'name': 'Rackspace'},
                           'RAX-AUTH:rsaCredentials': {
                               'tokenKey': self.rsa_token,
                               'username': self.username}}}
        output = bootstrap._build_auth_payload(self.username,
                                               rsa_token=self.rsa_token)
        self.assertEqual(wanted, output)

    def test_auth_with_password(self):
        wanted = {'auth': {'RAX-AUTH:domain': {'name': 'Rackspace'},
                           'passwordCredentials': {
                               'password': self.password,
                               'username': self.username}}}
        output = bootstrap._build_auth_payload(self.username,
                                               password=self.password)
        self.assertEqual(wanted, output)

    def test_auth_with_apikey(self):
        wanted = {'auth': {'RAX-AUTH:domain': {'name': 'Rackspace'},
                           'RAX-KSKEY:apiKeyCredentials': {
                               'apikey': self.apikey,
                               'username': self.username}}}
        output = bootstrap._build_auth_payload(self.username,
                                               apikey=self.apikey)
        self.assertEqual(wanted, output)

    def test_no_credential(self):
        self.assertRaises(TypeError, bootstrap._build_auth_payload,
                          self.username)

