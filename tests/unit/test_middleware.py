# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import unittest
import os

from checkmate.middleware import (TenantMiddleware,
                                  StripPathMiddleware,
                                  ExtensionsMiddleware,
                                  ContextMiddleware)
from bottle import request


class MockWsgiApp(object):

    def __init__(self):
        pass

    def __call__(self, env, start_response):
        pass


def _start_response():
    pass


class StripPathMiddlewareTest(unittest.TestCase):
    def setUp(self):
        self.filter = StripPathMiddleware(MockWsgiApp())

    def test_trailing_slash(self):
        env = {'PATH_INFO': '/something/'}
        self.filter(env, _start_response)
        self.assertEqual('/something', env['PATH_INFO'])

    def test_remove_trailing_slash_from_empty_path(self):
        """Test root"""
        env = {'PATH_INFO': '/'}
        self.filter(env, _start_response)
        self.assertEqual('', env['PATH_INFO'])


class TenantMiddlewareTest(unittest.TestCase):
    def setUp(self):
        self.filter = ContextMiddleware(TenantMiddleware(MockWsgiApp()))

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


class ExtensionsMiddlewareTest(unittest.TestCase):
    def setUp(self):
        self.filter = ExtensionsMiddleware(MockWsgiApp())

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


class RequestContextTest(unittest.TestCase):
    def setUp(self):
        self.filter = ContextMiddleware(MockWsgiApp())
        # Remove CHECKMATE_OVERRIDE_URL before running!
        if os.environ.get('CHECKMATE_OVERRIDE_URL'):
            del os.environ['CHECKMATE_OVERRIDE_URL']

    def test_populate_url_from_os_environ(self):
        os.environ['CHECKMATE_OVERRIDE_URL'] = 'http://OVERRIDDEN'
        self.filter({}, _start_response)
        self.assertEquals('http://OVERRIDDEN', request.context.base_url)

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
        self.assertEquals('http://MOCK', request.context.base_url)

    def test_server_name(self):
        env = {'PATH_INFO': '/',
               'wsgi.url_scheme': 'http',
               'SERVER_NAME': 'MOCK',
               'SERVER_PORT': '80'}
        self.filter(env, _start_response)
        self.assertEquals('http://MOCK', request.context.base_url)

    def test_https_weird_port(self):
        env = {'PATH_INFO' : '/',
               'wsgi.url_scheme': 'https',
               'SERVER_NAME': 'MOCK',
               'SERVER_PORT': '444'}
        self.filter(env, _start_response)
        self.assertEquals('https://MOCK:444', request.context.base_url)

    def test_http_weird_port(self):
        env = {'PATH_INFO' : '/',
               'wsgi.url_scheme': 'http',
               'SERVER_NAME': 'MOCK',
               'SERVER_PORT': '81'}
        self.filter(env, _start_response)
        self.assertEquals('http://MOCK:81', request.context.base_url)


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
