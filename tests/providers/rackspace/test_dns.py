#!/usr/bin/env python
import logging
import os
import unittest2 as unittest

import mox
from mox import IgnoreArg
import tldextract

from checkmate.providers.rackspace import dns
from checkmate.middleware import RequestContext

LOG = logging.getLogger(__name__)

try:
    from eventlet.green import socket
    # Test for internet connection using rackspace.com
    response = socket.getaddrinfo(
        'www.rackspace.com', 80, 0, 0, socket.TCP_NODELAY)
    SKIP = False
    REASON = None
except socket.gaierror as exc:
    LOG.warn("No network connection so skipping DNS tests: %s", exc)
    SKIP = True
    REASON = "No network connection: %s" % exc


class TestDnsProvider(unittest.TestCase):

    def __init__(self, methodName='runTest'):
        unittest.TestCase.__init__(self, methodName=methodName)
        self.mox = mox.Mox()

    def verify_limits(self, existing_doms, max_doms, max_records):
        """ Test the verify_limits() method """

        resources = [{
            "type": "dns-record",
            "interface": "A",
            "dns-name": "foo.example.com"
        }, {
            "type": "dns-record",
            "interface": "A",
            "dns-name": "bar.example.com"
        }]
        limits = {
            "absolute": {
                "domains": max_doms,
                "records per domain": max_records
            }
        }
        context = RequestContext()
        context.catalog = {
        }
        mock_api = self.mox.CreateMockAnything()
        self.mox.StubOutWithMock(dns.Provider, 'connect')
        dns.Provider.connect(IgnoreArg()).AndReturn(mock_api)
        self.mox.StubOutWithMock(dns.Provider, "_get_limits")
        (dns.Provider._get_limits(IgnoreArg(), IgnoreArg())
         .AndReturn(limits))
        mock_api.get_total_domain_count().AndReturn(existing_doms)
        dns.Provider.connect(IgnoreArg()).AndReturn(mock_api)
        mock_api.list_domains_info(filter_by_name=IgnoreArg()).AndReturn(None)
        dns.Provider.connect(IgnoreArg()).AndReturn(mock_api)
        mock_api.list_domains_info(filter_by_name=IgnoreArg()).AndReturn(None)
        self.mox.ReplayAll()
        result = dns.Provider({}).verify_limits(context, resources)
        self.mox.VerifyAll()
        return result

    def test_verify_limits_negative(self):
        """Test that verify_limits() returns warnings if limits are not okay"""
        result = self.verify_limits(1, 1, 0)
        LOG.debug(result)
        self.assertEqual(2, len(result))
        self.assertEqual(result[0]['type'], "INSUFFICIENT-CAPACITY")

    def test_verify_access_positive(self):
        """Test that verify_access() returns ACCESS-OK if user has access"""
        context = RequestContext()
        context.roles = 'identity:user-admin'
        provider = dns.Provider({})
        result = provider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')
        context.roles = 'dnsaas:admin'
        result = provider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')
        context.roles = 'dnsaas:creator'
        result = provider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')

    def test_verify_access_negative(self):
        """Test that verify_access() returns ACCESS-OK if user has access"""
        context = RequestContext()
        context.roles = 'dnsaas:observer'
        provider = dns.Provider({})
        result = provider.verify_access(context)
        self.assertEqual(result['type'], 'NO-ACCESS')


@unittest.skipIf(SKIP, REASON)
class TestParseDomain(unittest.TestCase):
    """ Test DNS Provider modules parse_domain function """

    def setUp(self):
        self.sample_domain = ('www.sample.com', 'sample.com')
        tld_path = os.path.dirname(tldextract.__file__)
        self.default_tld_cache_file = os.path.join(tld_path, '.tld_set')
        self.tld_cache_env = 'CHECKMATE_TLD_CACHE_FILE'
        self.custom_tld_cache_file = os.path.join(os.path.dirname(__file__),
                                                  'tld_set.tmp')
        self.sample_data = [
            self.sample_domain,
            ('ftp.regaion1.sample.com', 'sample.com'),
            ('ftp.regaion1.sample.net', 'sample.net'),
            ('ftp.regaion1.sample.co.uk', 'sample.co.uk')
        ]
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()
        if os.path.exists(self.custom_tld_cache_file):
            os.remove(self.custom_tld_cache_file)

    def test_parse_domain_without_custom_cache(self):
        if os.path.exists(self.default_tld_cache_file):
            try:
                os.remove(self.default_tld_cache_file)
            except Exception:
                # Not that big a deal if the file couldn't be removed by the
                # user running the test.
                pass
        if self.tld_cache_env in os.environ:
            os.environ.pop(self.tld_cache_env)
        domain, expected = self.sample_domain

        # Detect permission failure, log it, and let the test pass

        tldlog = dns.tldextract.tldextract.LOG
        self.mox.StubOutWithMock(tldlog, 'warn')
        self.save_failed = False

        def failed(*args):
            LOG.warn("A tldextract test failure is being ignored")
            LOG.warn(*args)
            self.save_failed = True

        tldlog.warn(
            "unable to cache TLDs in file %s: %s",
            self.default_tld_cache_file, mox.IgnoreArg()
        ).WithSideEffects(failed)
        self.mox.ReplayAll()

        answer = dns.parse_domain(domain)
        self.assertEquals(answer, expected)
        if not self.save_failed:
            self.assertTrue(os.path.exists(self.default_tld_cache_file))

    def test_parse_domain_with_custom_cache(self):
        if os.path.exists(self.custom_tld_cache_file):
            os.remove(self.custom_tld_cache_file)
        os.environ[self.tld_cache_env] = self.custom_tld_cache_file
        domain, expected = self.sample_domain
        answer = dns.parse_domain(domain)
        self.assertEquals(answer, expected)
        self.assertTrue(os.path.exists(self.custom_tld_cache_file))

    def test_sample_data(self):
        for domain, expected in self.sample_data:
            answer = dns.parse_domain(domain)
            self.assertEquals(answer, expected)

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
