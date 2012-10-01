#!/usr/bin/env python
import copy
import logging
import unittest2 as unittest

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging

from checkmate.middleware import TenantMiddleware, StripPathMiddleware, \
        ExtensionsMiddleware, ContextMiddleware


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
        env = {'PATH_INFO': '/'}
        self.filter(env, _start_response)
        self.assertEqual('/', env['PATH_INFO'])

    def test_tenant_only(self):
        env = {'PATH_INFO': '/T1000'}
        self.filter(env, _start_response)
        self.assertEqual('/', env['PATH_INFO'])

    def test_with_resource(self):
        env = {'PATH_INFO': '/T1000/deployments'}
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


if __name__ == '__main__':
    # Run tests. Handle our paramsters separately
    import sys
    args = sys.argv[:]
    # Our --debug means --verbose for unitest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)