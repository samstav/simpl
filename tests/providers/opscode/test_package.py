# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import unittest2 as unittest

from checkmate.providers import opscode
from checkmate.providers import base


class TestPackage(unittest.TestCase):
    def test_package_registration(self):
        base.PROVIDER_CLASSES = {}
        opscode.register()
        self.assertIn('opscode.chef-server', base.PROVIDER_CLASSES)
        self.assertIn('opscode.chef-solo', base.PROVIDER_CLASSES)
        self.assertEqual(len(base.PROVIDER_CLASSES), 2, msg="Check that all "
                         "your providers are registered and tested for")


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
