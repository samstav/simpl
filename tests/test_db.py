#!/usr/bin/env python
import logging
import os
import unittest2 as unittest

from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

os.environ['CHECKMATE_CONNECTION_STRING'] = 'sqlite://'
from checkmate import db
from checkmate.utils import extract_sensitive_data


class TestDatabase(unittest.TestCase):
    """ Test Database code """

    def setUp(self):
        self.driver = db.get_driver('checkmate.db.sql.Driver')

    def test_components(self):
        entity = {'id': 1,
                  'name': 'My Component',
                  'credentials': ['My Secrets']
                 }
        body, secrets = extract_sensitive_data(entity)
        results = self.driver.save_component(entity['id'], body, secrets,
            tenant_id='T1000')
        self.assertDictEqual(results, body)

        results = self.driver.get_component(entity['id'], with_secrets=True)
        entity['tenantId'] = 'T1000'  # gets added
        self.assertDictEqual(results, entity)
        self.assertIn('credentials', results)

        body['name'] = 'My Updated Component'
        entity['name'] = 'My Updated Component'
        results = self.driver.save_component(entity['id'], body)

        results = self.driver.get_component(entity['id'], with_secrets=True)
        self.assertIn('credentials', results)
        self.assertDictEqual(results, entity)

        results = self.driver.get_component(entity['id'], with_secrets=False)
        self.assertNotIn('credentials', results)
        body['tenantId'] = 'T1000'  # gets added
        self.assertDictEqual(results, body)


if __name__ == '__main__':
    # Run tests. Handle our parameters seprately
    import sys
    args = sys.argv[:]
    # Our --debug means --verbose for unittest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
