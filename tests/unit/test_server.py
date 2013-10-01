# pylint: disable=R0904
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

"""Tests for Schema module."""
import unittest

import bottle
import mock

from checkmate import exceptions
from checkmate import server
from checkmate import utils


class TestServerErrorParsing(unittest.TestCase):
    """Check that error formatting writes correct content and safe data."""

    @mock.patch.object(server.bottle, 'request')
    @mock.patch.object(server.bottle, 'response')
    @mock.patch.object(utils, 'write_body')
    def test_default_message(self, mock_write, mock_response, mock_request):
        """Error response is the safe default for non-checkmate exceptions."""
        exception = Exception('test')
        error = bottle.HTTPError(exception=exception)
        server.error_formatter(error)
        expected = {
            'error': {
                'code': 500,
                'message': 'Internal Server Error',
                'description': exceptions.UNEXPECTED_ERROR
            }
        }
        mock_write.assert_called_with(expected, mock_request, mock_response)

    @mock.patch.object(server.bottle, 'request')
    @mock.patch.object(server.bottle, 'response')
    @mock.patch.object(utils, 'write_body')
    def test_default_checkmate_message(self, mock_write, mock_response,
                                       mock_request):
        """Error response is the safe default for CheckmateExceptions."""
        exception = exceptions.CheckmateException('test')
        error = bottle.HTTPError(exception=exception)
        server.error_formatter(error)
        expected = {
            'error': {
                'code': 500,
                'message': 'Internal Server Error',
                'description': exceptions.UNEXPECTED_ERROR
            }
        }
        mock_write.assert_called_with(expected, mock_request, mock_response)

    @mock.patch.object(server.bottle, 'request')
    @mock.patch.object(server.bottle, 'response')
    @mock.patch.object(utils, 'write_body')
    def test_friendly_checkmate_message(self, mock_write, mock_response,
                                        mock_request):
        """Error response is the safe default for CheckmateExceptions."""
        exception = exceptions.CheckmateException(
            'test', friendly_message="Hi!")
        error = bottle.HTTPError(exception=exception)
        server.error_formatter(error)
        expected = {
            'error': {
                'code': 500,
                'message': 'Internal Server Error',
                'description': "Hi!"
            }
        }
        mock_write.assert_called_with(expected, mock_request, mock_response)

    @mock.patch.object(server.bottle, 'request')
    @mock.patch.object(server.bottle, 'response')
    @mock.patch.object(utils, 'write_body')
    def test_content_yaml(self, mock_write, mock_response, mock_request):
        """Error response is in yaml if accepts requests it."""
        mock_request.get_header.return_value = 'application/x-yaml'
        exception = exceptions.CheckmateException('test')
        error = bottle.HTTPError(exception=exception)
        server.error_formatter(error)
        expected = {
            'error': {
                'code': 500,
                'message': 'Internal Server Error',
                'description': exceptions.UNEXPECTED_ERROR
            }
        }
        mock_write.assert_called_with(expected, mock_request, mock_response)
        self.assertIsInstance(error.headers, bottle.HeaderDict)
        self.assertEqual(error.headers["content-type"], "application/x-yaml")


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
