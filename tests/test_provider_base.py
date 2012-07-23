#!/usr/bin/env python
import logging
import unittest2 as unittest


# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()

from checkmate.providers.base import ProviderBase, CheckmateInvalidProvider
from checkmate.utils import yaml_to_dict

LOG = logging.getLogger(__name__)


class TestProviderBase(unittest.TestCase):
    def test_provider_bad_override(self):
        """Raise error if invalid provider data passed in"""
        # Common mistake, pass object with key as base, instead of object
        data = yaml_to_dict("""
              base:
                  provides:
                  - widget: foo
                  vendor: test
            """)
        self.assertRaises(CheckmateInvalidProvider, ProviderBase, data)

    def test_provider_catalog_override(self):
        """Test that an injected catalog works"""
        data = yaml_to_dict("""
                  provides:
                  - widget: foo
                  - widget: bar
                  vendor: test
                  catalog:
                    widget:
                      small_widget:
                        is: widget
                        provides:
                        - widget: foo
                      big_widget:
                        is: widget
                        provides:
                        - widget: bar
            """)
        base = ProviderBase(data, key='base')
        self.assertDictEqual(base.get_catalog(None), data['catalog'])

    def test_provider_find_components(self):
        base = ProviderBase(yaml_to_dict("""
                  provides:
                  - widget: foo
                  - widget: bar
                  vendor: test
                  catalog:
                    widget:
                      small_widget:
                        is: widget
                        provides:
                        - widget: foo
                      big_widget:
                        is: widget
                        provides:
                        - widget: bar
            """), key='base')

        found = base.find_components(None, resource_type='widget')
        self.assertEqual(len(found), 2)
        self.assertIn(found[0]['id'], ['small_widget', 'big_widget'])
        self.assertIn(found[1]['id'], ['small_widget', 'big_widget'])

    def test_provider_select_components(self):
        """Correctly selects from components with same interface or type"""
        base = ProviderBase(yaml_to_dict("""
                  provides:
                  - widget: foo
                  - widget: bar
                  - gadget: foo
                  vendor: test
                  catalog:
                    widget:
                      small_widget:
                        is: widget
                        provides:
                        - widget: foo
                      big_widget:
                        is: widget
                        provides:
                        - widget: bar
                      gadget:
                        is: gadget
                        provides:
                        - gadget: foo
            """), key='base')

        found = base.find_components(None, resource_type='widget')
        self.assertEqual(len(found), 2)
        self.assertIn(found[0]['id'], ['small_widget', 'big_widget'])
        self.assertIn(found[1]['id'], ['small_widget', 'big_widget'])

        found = base.find_components(None, resource_type='gadget')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['id'], 'gadget')

        found = base.find_components(None, interface='foo')
        self.assertEqual(len(found), 2)
        self.assertIn(found[0]['id'], ['small_widget', 'gadget'])
        self.assertIn(found[1]['id'], ['small_widget', 'gadget'])

        found = base.find_components(None, resource_type='widget',
                interface='foo')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['id'], 'small_widget',)


if __name__ == '__main__':
    # Run tests. Handle our paramsters separately
    import sys
    args = sys.argv[:]
    # Our --debug means --verbose for unitest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main()
