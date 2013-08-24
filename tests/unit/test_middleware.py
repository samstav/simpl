# pylint: disable=C0103,R0904

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

"""Tests for middleware."""
import os
import unittest

import bottle

from checkmate import middleware as cmmid


def _start_response():
    "Helper method to mock _start_response."""
    pass


class MockWsgiApp(object):
    """Mock class for the WsgiApp."""
    def __init__(self):
        pass

    def __call__(self, env, start_response):
        pass


class TestStripPathMiddleware(unittest.TestCase):
    def setUp(self):
        self.filter = cmmid.StripPathMiddleware(MockWsgiApp())

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
        self.filter = cmmid.ContextMiddleware(
            cmmid.TenantMiddleware(MockWsgiApp()))

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
        self.filter = cmmid.ExtensionsMiddleware(MockWsgiApp())

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


class TestRequestContext(unittest.TestCase):
    def setUp(self):
        self.filter = cmmid.ContextMiddleware(MockWsgiApp())
        # Remove CHECKMATE_OVERRIDE_URL before running!
        if os.environ.get('CHECKMATE_OVERRIDE_URL'):
            del os.environ['CHECKMATE_OVERRIDE_URL']

    def test_populate_url_from_os_environ(self):
        os.environ['CHECKMATE_OVERRIDE_URL'] = 'http://OVERRIDDEN'
        self.filter({}, _start_response)
        self.assertEquals('http://OVERRIDDEN', bottle.request.context.base_url)

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
        self.assertEquals('http://MOCK', bottle.request.context.base_url)

    def test_server_name(self):
        env = {'PATH_INFO': '/',
               'wsgi.url_scheme': 'http',
               'SERVER_NAME': 'MOCK',
               'SERVER_PORT': '80'}
        self.filter(env, _start_response)
        self.assertEquals('http://MOCK', bottle.request.context.base_url)

    def test_https_weird_port(self):
        env = {'PATH_INFO': '/',
               'wsgi.url_scheme': 'https',
               'SERVER_NAME': 'MOCK',
               'SERVER_PORT': '444'}
        self.filter(env, _start_response)
        self.assertEquals('https://MOCK:444', bottle.request.context.base_url)

    def test_http_weird_port(self):
        env = {'PATH_INFO': '/',
               'wsgi.url_scheme': 'http',
               'SERVER_NAME': 'MOCK',
               'SERVER_PORT': '81'}
        self.filter(env, _start_response)
        self.assertEquals('http://MOCK:81', bottle.request.context.base_url)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
