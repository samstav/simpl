import unittest

from checkmate.providers import core
from checkmate.providers import base


class TestPackage(unittest.TestCase):
    def test_package_registration(self):
        base.PROVIDER_CLASSES = {}
        core.register()
        self.assertIn('core.script', base.PROVIDER_CLASSES)
        self.assertEqual(len(base.PROVIDER_CLASSES), 1, msg="Check that all "
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
