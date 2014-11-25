# pylint: disable=C0103,E1101,R0904,W0212,E1120

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

"""Tests for Rackspace DNS provider."""
import logging
import os
import unittest

import mox
import pyrax

from checkmate import middleware as cmmid
from checkmate.providers.rackspace import dns
from checkmate.providers.rackspace.dns import provider

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
        """Test the verify_limits() method."""

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
        context = cmmid.RequestContext()
        context.catalog = {
        }
        mock_api = self.mox.CreateMockAnything()
        self.mox.StubOutWithMock(dns.provider.Provider, 'connect')
        dns.provider.Provider.connect(mox.IgnoreArg()).AndReturn(mock_api)
        self.mox.StubOutWithMock(dns.provider.Provider, "_get_limits")
        (dns.provider.Provider._get_limits(mox.IgnoreArg(), mox.IgnoreArg())
         .AndReturn(limits))
        mock_api.list().AndReturn(existing_doms)
        mock_api.list_next_page().AndRaise(pyrax.exceptions.NoMoreResults())
        dns.provider.Provider.connect(mox.IgnoreArg()).AndReturn(mock_api)
        mock_api.find(name=mox.IgnoreArg()).AndReturn(None)

        dns.provider.Provider.connect(mox.IgnoreArg()).AndReturn(mock_api)
        mock_api.find(name=mox.IgnoreArg()).AndReturn(None)
        dns.provider.Provider.connect(mox.IgnoreArg()).AndReturn(mock_api)
        mock_api.find(name=mox.IgnoreArg()).AndReturn(None)
        self.mox.ReplayAll()
        result = dns.provider.Provider({}).verify_limits(context, resources)
        self.mox.VerifyAll()
        return result

    def test_verify_limits_negative(self):
        """Test that verify_limits() returns warning if limits exceeded."""
        result = self.verify_limits([1], 1, 0)
        self.assertEqual(2, len(result))
        self.assertEqual(result[0]['type'], "INSUFFICIENT-CAPACITY")

    def test_verify_access_positive(self):
        """Test that verify_access() returns ACCESS-OK if user has access."""
        context = cmmid.RequestContext()
        context.roles = 'identity:user-admin'
        dnsprovider = dns.provider.Provider({})
        result = dnsprovider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')
        context.roles = 'dnsaas:admin'
        result = dnsprovider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')
        context.roles = 'dnsaas:creator'
        result = dnsprovider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')

    def test_verify_access_negative(self):
        """Test that verify_access() returns ACCESS-OK if user has access."""
        context = cmmid.RequestContext()
        context.roles = 'dnsaas:observer'
        dnsprovider = dns.provider.Provider({})
        result = dnsprovider.verify_access(context)
        self.assertEqual(result['type'], 'NO-ACCESS')


@unittest.skipIf(SKIP, REASON)
class TestParseDomain(unittest.TestCase):
    def setUp(self):
        self.sample_domain = ('www.sample.com', 'sample.com')
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
        if self.tld_cache_env in os.environ:
            os.environ.pop(self.tld_cache_env)
        domain, expected = self.sample_domain

        answer = provider.parse_domain(domain)
        self.assertEquals(answer, expected)

    def test_parse_domain_with_custom_cache(self):
        if os.path.exists(self.custom_tld_cache_file):
            os.remove(self.custom_tld_cache_file)
        os.environ[self.tld_cache_env] = self.custom_tld_cache_file
        domain, expected = self.sample_domain
        answer = provider.parse_domain(domain)
        self.assertEquals(answer, expected)
        self.assertTrue(os.path.exists(self.custom_tld_cache_file))

    def test_sample_data(self):
        for domain, expected in self.sample_data:
            answer = provider.parse_domain(domain)
            self.assertEquals(answer, expected)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
