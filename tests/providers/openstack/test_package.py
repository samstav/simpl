"""Tests for OpenStack package registration."""
import unittest

from checkmate.providers import openstack
from checkmate.providers import base


class TestPackage(unittest.TestCase):
    def test_package_registration(self):
        base.PROVIDER_CLASSES = {}
        openstack.register()
        self.assertIn('openstack.compute', base.PROVIDER_CLASSES)
        self.assertEqual(len(base.PROVIDER_CLASSES), 1, msg="Check that all "
                         "your providers are registered and tested for")


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
