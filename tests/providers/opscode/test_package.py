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
    # Run tests. Handle our parameters separately
    import sys
    args = sys.argv[:]
    # Our --debug means --verbose for unittest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
