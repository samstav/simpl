# pylint: disable=C0103,R0904,R0903

# Copyright (c) 2011-2015 Rackspace US, Inc.
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

"""Tests for middleware."""
import os
import unittest

import webob

from checkmate import middleware


def _start_response(environ, handler):
    "Helper method to mock _start_response."""
    pass


class MockWsgiApp(object):
    """Mock class for the WsgiApp."""
    def __init__(self):
        pass

    def __call__(self, env, start_response):
        pass


class TestGenerateResponse(unittest.TestCase):
    """Test the webob patch."""
    def setUp(self):
        self.http_exception = webob.exc.WSGIHTTPException()
        self.environ = {'REQUEST_METHOD': 'GET'}

    def test_html_error(self):
        self.environ['HTTP_ACCEPT'] = 'text/html'
        results = middleware.generate_response(self.http_exception,
                                               self.environ,
                                               _start_response)
        self.assertIn("<html>", results[0])

    def test_yaml_error(self):
        self.environ['HTTP_ACCEPT'] = 'application/x-yaml'
        results = middleware.generate_response(self.http_exception,
                                               self.environ,
                                               _start_response)
        self.assertIn("error:\n", results[0])

    def test_json_error(self):
        self.environ['HTTP_ACCEPT'] = 'application/json'
        results = middleware.generate_response(self.http_exception,
                                               self.environ,
                                               _start_response)
        self.assertIn("""{\n    "error": {\n""", results[0])


class TestStripPathMiddleware(unittest.TestCase):
    def setUp(self):
        self.filter = middleware.StripPathMiddleware(MockWsgiApp())

    def test_trailing_slash(self):
        env = {'PATH_INFO': '/something/'}
        self.filter(env, _start_response)
        self.assertEqual('/something', env['PATH_INFO'])

    def test_remove_trailing_slash_from_empty_path(self):
        env = {'PATH_INFO': '/'}
        self.filter(env, _start_response)
        self.assertEqual('', env['PATH_INFO'])


class TestTenantMiddleware(unittest.TestCase):
    def setUp(self):
        self.filter = middleware.ContextMiddleware(
            middleware.TenantMiddleware(MockWsgiApp()))

    def test_no_tenant(self):
        env = {'PATH_INFO': '/',
               'wsgi.url_scheme': 'http',
               'HTTP_HOST': 'MOCK'}
        self.filter(env, _start_response)
        self.assertEqual('/', env['PATH_INFO'])

    def test_tenant_only(self):
        env = {'PATH_INFO': '/T1000',
               'wsgi.url_scheme': 'http',
               'HTTP_HOST': 'MOCK'}
        self.filter(env, _start_response)
        self.assertEqual('/', env['PATH_INFO'])

    def test_with_resource(self):
        env = {'PATH_INFO': '/T1000/deployments',
               'wsgi.url_scheme': 'http',
               'HTTP_HOST': 'MOCK'}
        self.filter(env, _start_response)
        self.assertEqual('/deployments', env['PATH_INFO'])


class TestExtensionsMiddleware(unittest.TestCase):
    def setUp(self):
        self.filter = middleware.ExtensionsMiddleware(MockWsgiApp())

    def test_no_extension(self):
        env = {'PATH_INFO': '/someresource'}
        self.filter(env, _start_response)
        self.assertEqual('/someresource', env['PATH_INFO'])
        self.assertNotIn('HTTP_ACCEPT', env)

    def test_yaml_extension(self):
        env = {'PATH_INFO': '/someresource.yaml'}
        self.filter(env, _start_response)
        self.assertEqual('/someresource', env['PATH_INFO'])
        self.assertEqual('application/x-yaml', env['HTTP_ACCEPT'])

    def test_json_extension(self):
        env = {'PATH_INFO': '/someresource.json'}
        self.filter(env, _start_response)
        self.assertEqual('/someresource', env['PATH_INFO'])
        self.assertEqual('application/json', env['HTTP_ACCEPT'])

    def test_extension_overrides_header(self):
        env = {
            'PATH_INFO': '/someresource.json',
            'HTTP_ACCEPT': 'application/yaml'}
        self.filter(env, _start_response)
        self.assertEqual('/someresource', env['PATH_INFO'])
        self.assertEqual('application/json', env['HTTP_ACCEPT'])


class RequestContextTests(unittest.TestCase):
    """RequestContextTests"""
    def test_dict_conversion(self):
        context = middleware.RequestContext(simulation='True',
                                            param1='value1', param2='value2')
        data = context.get_queued_task_dict(param3='value3')
        self.assertDictContainsSubset({'param1': 'value1',
                                       'param2': 'value2',
                                       'param3': 'value3',
                                       'simulation': 'True'}, data)
        data2 = context.get_queued_task_dict()
        self.assertDictContainsSubset({'param1': 'value1',
                                       'param2': 'value2',
                                       'simulation': 'True'}, data2)


class TestRequestContext(unittest.TestCase):
    def setUp(self):
        self.filter = middleware.ContextMiddleware(MockWsgiApp())
        # Remove CHECKMATE_OVERRIDE_URL before running!
        if os.environ.get('CHECKMATE_OVERRIDE_URL'):
            del os.environ['CHECKMATE_OVERRIDE_URL']

    def test_populate_url_from_os_environ(self):
        os.environ['CHECKMATE_OVERRIDE_URL'] = 'http://OVERRIDDEN'
        env = {}
        self.filter(env, _start_response)
        self.assertEqual('http://OVERRIDDEN', env['context'].base_url)

    def test_no_url_scheme(self):
        with self.assertRaises(KeyError):
            self.filter({}, _start_response)

    def test_no_http_host_no_server_name(self):
        env = {'PATH_INFO': '/',
               'wsgi.url_scheme': 'http'}
        with self.assertRaises(KeyError):
            self.filter(env, _start_response)

    def test_server_name_no_server_port(self):
        env = {'PATH_INFO': '/',
               'wsgi.url_scheme': 'http',
               'SERVER_NAME': 'MOCK'}
        with self.assertRaises(KeyError):
            self.filter(env, _start_response)

    def test_http_host(self):
        env = {'PATH_INFO': '/',
               'wsgi.url_scheme': 'http',
               'HTTP_HOST': 'MOCK'}
        self.filter(env, _start_response)
        self.assertEqual('http://MOCK', env['context'].base_url)

    def test_server_name(self):
        env = {'PATH_INFO': '/',
               'wsgi.url_scheme': 'http',
               'SERVER_NAME': 'MOCK',
               'SERVER_PORT': '80'}
        self.filter(env, _start_response)
        self.assertEqual('http://MOCK', env['context'].base_url)

    def test_https_weird_port(self):
        env = {'PATH_INFO': '/',
               'wsgi.url_scheme': 'https',
               'SERVER_NAME': 'MOCK',
               'SERVER_PORT': '444'}
        self.filter(env, _start_response)
        self.assertEqual('https://MOCK:444', env['context'].base_url)

    def test_http_weird_port(self):
        env = {'PATH_INFO': '/',
               'wsgi.url_scheme': 'http',
               'SERVER_NAME': 'MOCK',
               'SERVER_PORT': '81'}
        self.filter(env, _start_response)
        self.assertEqual('http://MOCK:81', env['context'].base_url)


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
