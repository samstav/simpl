#!/usr/bin/env python
import logging
import unittest2 as unittest

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
import os
import tldextract
from checkmate.providers.rackspace import dns
init_console_logging()
LOG = logging.getLogger(__name__)


class TestParseDomain(unittest.TestCase):
    """ Test DNS Provider modules parse_domain function """

    def setUp(self):
        self.sample_domain = ('www.sample.com', 'sample.com')
        self.default_tld_cache_file = ('%s/.tld_set' %
                                       os.path.dirname(tldextract.__file__))
        self.tld_cache_env = 'CHECKMATE_TLD_CACHE_FILE'
        self.custom_tld_cache_file = ('%s/tld_set.tmp' %
                                      os.path.dirname(__file__))
        self.sample_data = [
                            self.sample_domain,
                            ('ftp.regaion1.sample.com', 'sample.com'),
                            ('ftp.regaion1.sample.net', 'sample.net'),
                            ('ftp.regaion1.sample.co.uk', 'sample.co.uk')
                            ]

    def tearDown(self):
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
        answer = dns.parse_domain(domain)
        self.assertEquals(answer, expected)
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
