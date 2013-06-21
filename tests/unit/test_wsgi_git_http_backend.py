import unittest
from mock import patch, Mock, mock_open
import os
from checkmate import wsgi_git_http_backend

'''
[*] wsgi_to_git_http_backend
run_git_http_backend
build_cgi_environ
parse_cgi_header
_communicate_with_git
_input_data_pump
_find_header_end_in_2_chunks
[*] _search_str_for_header_end
_separate_header
_response_body_generator
'''

class TestWsgiGitHttpBackend_wsgi_to_git_http_backend(unittest.TestCase):

    @patch.object(wsgi_git_http_backend, 'build_cgi_environ')
    @patch.object(wsgi_git_http_backend, 'run_git_http_backend')
    @patch.object(wsgi_git_http_backend, 'parse_cgi_header')
    #@unittest.skip("Temp skip")
    def test_mocked_up(self,mock_parse,mock_run,mock_build):
        # mocks
        mock_build.return_value = {}
        mock_run.return_value = {'foo':'bar'}, {'foo':'bar'}
        mock_parse.return_value = 200,{'foo':'bar'}
        # kick off
        response = wsgi_git_http_backend.wsgi_to_git_http_backend({'wsgi.input':None,'wsgi.errors':None},None)
        assert mock_run.called
        assert mock_parse.called

class TestWsgiGitHttpBackend_run_git_http_backend(unittest.TestCase):

    @patch.object(wsgi_git_http_backend, 'subprocess')
    @patch.object(wsgi_git_http_backend, '_communicate_with_git')
    #@unittest.skip("Temp skip")
    def test_mocked_up(self,mock_comm,mock_subproc):
        # mocks
        mock_subproc.Popen.return_value = True
        mock_subproc.PIPE = Mock()
        mock_comm.return_value = {}, {}
        # kick off
        cgienv = {'CONTENT_LENGTH':10}
        response = wsgi_git_http_backend.run_git_http_backend(cgienv,None,None)
        assert mock_comm.called

class TestWsgiGitHttpBackend_build_cgi_environ(unittest.TestCase):

    @patch.object(wsgi_git_http_backend, 'subprocess')
    @patch.object(wsgi_git_http_backend, '_communicate_with_git')
    #@unittest.skip("Temp skip")
    def test_mocked_up(self,mock_comm,mock_subproc):
        # mocks
        mock_subproc.Popen.return_value = True
        mock_subproc.PIPE = Mock()
        mock_comm.return_value = {}, {}
        # kick off
        cgienv = {'CONTENT_LENGTH':10}
        response = wsgi_git_http_backend.run_git_http_backend(cgienv,None,None)
        assert mock_comm.called

class TestWsgiGitHttpBackend_build_cgi_header(unittest.TestCase):

    @patch.object(wsgi_git_http_backend, 'subprocess')
    @patch.object(wsgi_git_http_backend, '_communicate_with_git')
    #@unittest.skip("Temp skip")
    def test_mocked_up(self,mock_comm,mock_subproc):
        # mocks
        mock_subproc.Popen.return_value = True
        mock_subproc.PIPE = Mock()
        mock_comm.return_value = {}, {}
        # kick off
        cgienv = {'CONTENT_LENGTH':10}
        response = wsgi_git_http_backend.run_git_http_backend(cgienv,None,None)
        assert mock_comm.called

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

