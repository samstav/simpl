import unittest

from checkmate.providers import rackspace
from checkmate.providers import base


class TestPackage(unittest.TestCase):
    def test_package_registration(self):
        base.PROVIDER_CLASSES = {}
        rackspace.register()
        self.assertIn('rackspace.legacy', base.PROVIDER_CLASSES)
        self.assertIn('rackspace.nova', base.PROVIDER_CLASSES)
        self.assertIn('rackspace.database', base.PROVIDER_CLASSES)
        self.assertIn('rackspace.load-balancer', base.PROVIDER_CLASSES)
        self.assertIn('rackspace.dns', base.PROVIDER_CLASSES)
        self.assertIn('rackspace.files', base.PROVIDER_CLASSES)
        self.assertEqual(len(base.PROVIDER_CLASSES), 6, msg="Check that all "
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
