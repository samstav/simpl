# pylint: disable=C0103,E0602,R0201,R0904,W0212,W0612,W0613,R0913

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

"""Tests for WSGI git http backend."""
import mock
import unittest

from eventlet.green import threading

from checkmate.contrib import wsgi_git_http_backend

#TODO(any): [need help] _comm_with_git, _input_data_pump,
#           _response_body_generator
#TODO(any): _separate_header


class TestWsgiGitHttpBackendWsgiToGit(unittest.TestCase):

    @mock.patch.object(wsgi_git_http_backend, 'build_cgi_environ')
    @mock.patch.object(wsgi_git_http_backend, 'run_git_http_backend')
    @mock.patch.object(wsgi_git_http_backend, 'parse_cgi_header')
    def test_mocked_up(self, mock_parse, mock_run, mock_build):
        mock_build.return_value = {}
        mock_run.return_value = {'foo': 'bar'}, {'foo': 'bar'}
        mock_parse.return_value = 200, {'foo': 'bar'}
        wsgi_git_http_backend.wsgi_to_git_http_backend({
            'wsgi.input': None, 'wsgi.errors': None}, None)
        assert mock_run.called
        assert mock_parse.called


class TestWsgiGitHttpBackendRunGit(unittest.TestCase):
    @mock.patch.object(wsgi_git_http_backend, 'subprocess')
    @mock.patch.object(wsgi_git_http_backend, '_communicate_with_git')
    def test_mocked_up(self, mock_comm, mock_subproc):
        mock_subproc.Popen.return_value = True
        mock_subproc.PIPE = mock.Mock()
        mock_comm.return_value = {}, {}
        cgienv = {'CONTENT_LENGTH': 10}
        wsgi_git_http_backend.run_git_http_backend(
            cgienv, None, None
        )
        assert mock_comm.called


class TestWsgiGitHttpBackendBuildCgiEnviron(unittest.TestCase):
    @mock.patch.object(wsgi_git_http_backend, 'subprocess')
    @mock.patch.object(wsgi_git_http_backend, '_communicate_with_git')
    def test_mocked_up(self, mock_comm, mock_subproc):
        mock_subproc.Popen.return_value = True
        mock_subproc.PIPE = mock.Mock()
        mock_comm.return_value = {}, {}
        cgienv = {'CONTENT_LENGTH': 10}
        wsgi_git_http_backend.run_git_http_backend(
            cgienv, None, None
        )
        assert mock_comm.called


class TestWsgiGitHttpBackendParseCgiHeader(unittest.TestCase):
    @mock.patch.object(wsgi_git_http_backend, 'subprocess')
    @mock.patch.object(wsgi_git_http_backend, '_communicate_with_git')
    def test_mocked_up(self, mock_comm, mock_subproc):
        mock_subproc.Popen.return_value = True
        mock_subproc.PIPE = mock.Mock()
        mock_comm.return_value = {}, {}
        cgienv = {'CONTENT_LENGTH': 10}
        wsgi_git_http_backend.run_git_http_backend(
            cgienv, None, None
        )
        assert mock_comm.called


class TestWsgiGitHttpBackendCommWithGit(unittest.TestCase):
    @mock.patch.object(threading, 'Thread')
    @mock.patch.object(wsgi_git_http_backend, 'sum')
    @mock.patch.object(wsgi_git_http_backend, 'EnvironmentError')
    @mock.patch.object(wsgi_git_http_backend, '_find_header_end_in_2_chunks')
    @mock.patch.object(wsgi_git_http_backend, '_separate_header')
    @mock.patch.object(wsgi_git_http_backend, 'response_body_generator')
    @unittest.skip("Temp skip")
    def test_mocked_up(self, mock_gen, mock_sep, mock_find, mock_enverr,
                       mock_sum, mock_thread):
        mock_subproc = mock.Mock()
        mock_subproc.Popen.return_value = True
        mock_subproc.PIPE = mock.Mock()
        mock_find.return_value = (None, None)
        mock_sep.return_value = {}, 0
        mock_gen.return_value = True
        wsgi_git_http_backend._communicate_with_git('proc', 'in', 1)
        assert mock_gen.called


class TestWsgiGitHttpBackendFindHeaderEnd(unittest.TestCase):
    def test_end_in_first_arg(self):
        chunk0 = 'foo123456\r\n\r\nblah'
        chunk1 = 'abc\r\n\r\nyoyo'
        resp = wsgi_git_http_backend._find_header_end_in_2_chunks(
            chunk0, chunk1
        )
        self.assertEqual((False, 3), resp)


class TestWsgiGitHttpBackendSeparateHeader(unittest.TestCase):
    def test_end_on_boundary(self):
        pass

    def test_not_end_on_boundary(self):
        pass


class TestWsgiGitHttpBackendSearchForHeaderEnd(unittest.TestCase):
    def test_search_str_for_header_end_good(self):
        data_str = "foobar\r\n\r\nxyz"
        response = wsgi_git_http_backend._search_str_for_header_end(data_str)
        self.assertEqual(len('foobar'), response)

    def test_search_str_for_header_end_bad(self):
        data_str = "foobar\r\n\rxyz"
        response = wsgi_git_http_backend._search_str_for_header_end(data_str)
        self.assertEqual(-1, response)


if __name__ == '__main__':
    import sys
    from checkmate import test
    test.run_with_params(sys.argv[:])
