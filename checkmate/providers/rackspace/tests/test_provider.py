import unittest2 as unittest

from checkmate.providers import rackspace
from checkmate.providers import base


class TestProvider(unittest.TestCase):
    def test_provider_registration(self):
        base.PROVIDER_CLASSES = {}
        rackspace.register()
        self.assertIn('rackspace.legacy', base.PROVIDER_CLASSES)
        self.assertIn('rackspace.nova', base.PROVIDER_CLASSES)
        self.assertIn('rackspace.database', base.PROVIDER_CLASSES)
        self.assertIn('rackspace.load-balancer', base.PROVIDER_CLASSES)
        self.assertIn('rackspace.dns', base.PROVIDER_CLASSES)
        self.assertIn('rackspace.files', base.PROVIDER_CLASSES)


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
