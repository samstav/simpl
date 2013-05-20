#!/usr/bin/env python
import errno
import logging
import os
import unittest2 as unittest

import mox
import tldextract

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
from checkmate.providers.rackspace import dns
init_console_logging()
LOG = logging.getLogger(__name__)


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
