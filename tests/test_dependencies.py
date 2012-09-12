#!/usr/bin/env python
import logging
import unittest2 as unittest

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)


class TestDependencies(unittest.TestCase):
    """Test critical and unusual dependencies

    Unusual = forks of public projects, depedencies that need complicated
              libraries (like openssh), etc...
    """
    def test_python_version(self):
        """Test that we are running the python 2.7.1 or greater"""
        self.assertGreaterEqual(sys.version_info, (2, 7, 1), "Checkmate needs "
                                "python version 2.7.1 or later")

    def test_pycrypto_version(self):
        """Test that we can instantiate pycrypto"""
        import Crypto
        self.assertGreaterEqual(Crypto.version_info, (2, 6), "Checkmate "
                                "expects pycrypto version 2.6 or later")

    def test_paramiko_version(self):
        """Test that we can instantiate pycrypto"""
        import paramiko
        self.assertGreaterEqual(paramiko.__version_info__, (1, 7, 7, 1),
                                "Checkmate expects paramiko version 1.7.7.1 "
                                "or later")

    def test_pam_version(self):
        """Test that we can instantiate PAM"""
        import pam

    def test_celery_version(self):
        """Test that we can instantiate YAML"""
        import celery
        version = [int(part) for part in celery.__version__.split(".")]
        self.assertGreaterEqual(version, [3, 0, 9], "Checkmate expects celery "
                                "version 3.0.9 or later")

    def test_yaml_version(self):
        """Test that we can instantiate YAML"""
        import yaml
        version = [int(part) for part in yaml.__version__.split(".")]
        self.assertGreaterEqual(version, [3, 10], "Checkmate expects PyYAML "
                                "version 3.10 or later")

    def test_spiff_version(self):
        """Test that we can instantiate the right version of SpiffWorkflow"""
        import SpiffWorkflow
        version_info = SpiffWorkflow.version()
        self.assertIn("rackspace internal", version_info, "Checkmate needs "
                      "the Rackspace-extended version of SpiffWorkflow")
        version, info = SpiffWorkflow.version().split('-')[0:2]
        version = [int(part) for part in version.split(".")]
        self.assertGreaterEqual(version, [0, 3, 2], "Checkmate expects "
                                "SpiffWorkflow version 0.3.2 or later")


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
