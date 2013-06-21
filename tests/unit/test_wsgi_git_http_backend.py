import unittest
from mock import patch, Mock, mock_open
import os
from checkmate import wsgi_git_http_backend
from eventlet.green import threading, subprocess

#TODO: [need help] _comm_with_git, _input_data_pump, _response_body_generator
#TODO: _separate_header


class TestWsgiGitHttpBackend_wsgi_to_git_http_backend(unittest.TestCase):

    @patch.object(wsgi_git_http_backend, 'build_cgi_environ')
    @patch.object(wsgi_git_http_backend, 'run_git_http_backend')
    @patch.object(wsgi_git_http_backend, 'parse_cgi_header')
    #@unittest.skip("Temp skip")
    def test_mocked_up(self, mock_parse, mock_run, mock_build):
        # mocks
        mock_build.return_value = {}
        mock_run.return_value = {'foo': 'bar'}, {'foo': 'bar'}
        mock_parse.return_value = 200, {'foo': 'bar'}
        # kick off
        response = wsgi_git_http_backend.wsgi_to_git_http_backend({
            'wsgi.input': None, 'wsgi.errors': None}, None)
        assert mock_run.called
        assert mock_parse.called


class TestWsgiGitHttpBackend_run_git_http_backend(unittest.TestCase):

    @patch.object(wsgi_git_http_backend, 'subprocess')
    @patch.object(wsgi_git_http_backend, '_communicate_with_git')
    #@unittest.skip("Temp skip")
    def test_mocked_up(self, mock_comm, mock_subproc):
        # mocks
        mock_subproc.Popen.return_value = True
        mock_subproc.PIPE = Mock()
        mock_comm.return_value = {}, {}
        # kick off
        cgienv = {'CONTENT_LENGTH': 10}
        response = wsgi_git_http_backend.run_git_http_backend(
            cgienv, None, None
        )
        assert mock_comm.called


class TestWsgiGitHttpBackend_build_cgi_environ(unittest.TestCase):

    @patch.object(wsgi_git_http_backend, 'subprocess')
    @patch.object(wsgi_git_http_backend, '_communicate_with_git')
    #@unittest.skip("Temp skip")
    def test_mocked_up(self, mock_comm, mock_subproc):
        # mocks
        mock_subproc.Popen.return_value = True
        mock_subproc.PIPE = Mock()
        mock_comm.return_value = {}, {}
        # kick off
        cgienv = {'CONTENT_LENGTH': 10}
        response = wsgi_git_http_backend.run_git_http_backend(
            cgienv, None, None
        )
        assert mock_comm.called


class TestWsgiGitHttpBackend_parse_cgi_header(unittest.TestCase):

    @patch.object(wsgi_git_http_backend, 'subprocess')
    @patch.object(wsgi_git_http_backend, '_communicate_with_git')
    #@unittest.skip("Temp skip")
    def test_mocked_up(self, mock_comm, mock_subproc):
        # mocks
        mock_subproc.Popen.return_value = True
        mock_subproc.PIPE = Mock()
        mock_comm.return_value = {}, {}
        # kick off
        cgienv = {'CONTENT_LENGTH': 10}
        response = wsgi_git_http_backend.run_git_http_backend(
            cgienv, None, None
        )
        assert mock_comm.called


class TestWsgiGitHttpBackend_comm_with_git(unittest.TestCase):

    @patch.object(threading, 'Thread')
    @patch.object(wsgi_git_http_backend, 'sum')
    @patch.object(wsgi_git_http_backend, 'EnvironmentError')
    @patch.object(wsgi_git_http_backend, '_find_header_end_in_2_chunks')
    @patch.object(wsgi_git_http_backend, '_separate_header')
    @patch.object(wsgi_git_http_backend, 'response_body_generator')
    @unittest.skip("Temp skip")
    def test_mocked_up(
        self, mock_gen, mock_sep,
        mock_find, mock_enverr, mock_sum, mock_thread
    ):
        # mocks
        mock_subproc.Popen.return_value = True
        mock_subproc.PIPE = Mock()
        #mock_read.return_value = 'foobar'
        mock_find.return_value = (None, None)
        mock_sep.return_value = {}, 0
        mock_gen.return_value = True
        # kick off
        wsgi_git_http_backend._communicate_with_git('proc', 'in', 1)
        assert mock_resp.called


class TestWsgiGitHttpBackend_find_header_end_2_chunks(unittest.TestCase):

    #@unittest.skip("Temp skip")
    def test_end_in_first_arg(self):
        chunk0 = 'foo123456\r\n\r\nblah'
        chunk1 = 'abc\r\n\r\nyoyo'
        # kick off
        resp = wsgi_git_http_backend._find_header_end_in_2_chunks(
            chunk0, chunk1
        )
        self.assertEqual((False, 3), resp)


class TestWsgiGitHttpBackend_separate_header(unittest.TestCase):

    #@unittest.skip("Temp skip")
    def test_end_on_boundary(self):
        pass

    #@unittest.skip("Temp skip")
    def test_not_end_on_boundary(self):
        pass


class TestWsgiGitHttpBackend_search_str_for_header_end(unittest.TestCase):

    #@unittest.skip("Temp skip")
    def test_search_str_for_header_end_good(self):
        data_str = "foobar\r\n\r\nxyz"
        response = wsgi_git_http_backend._search_str_for_header_end(data_str)
        self.assertEqual(len('foobar'), response)

    #@unittest.skip("Temp skip")
    def test_search_str_for_header_end_bad(self):
        data_str = "foobar\r\n\rxyz"
        response = wsgi_git_http_backend._search_str_for_header_end(data_str)
        self.assertEqual(-1, response)
