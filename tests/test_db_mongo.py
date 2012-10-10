#!/usr/bin/env python
import logging
import os
import unittest2 as unittest
import uuid

from pymongo import Connection
from pymongo.errors import AutoReconnect, InvalidURI

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate import db

SKIP = False
REASON = ""
try:
    from checkmate.db import mongodb
except AutoReconnect:
    LOG.warn("Could not connect to mongodb. Skipping mongodb tests")
    SKIP = True
    REASON = "Could not connect to mongodb"
except InvalidURI:
    LOG.warn("Not configured for mongodb. Skipping mongodb tests")
    SKIP = True
    REASON = "Configured to connect to non-mongo URI"
from checkmate.utils import extract_sensitive_data


class TestDatabase(unittest.TestCase):
    """ Test Mongo Database code """

    def setUp(self):
        self.db_name = 'checkmate_test_%s' % uuid.uuid4().hex
        self.driver = db.get_driver('checkmate.db.mongodb.Driver')
        self.driver.connection_string = 'mongodb://localhost/%s' % self.db_name
        self.driver._connection = self.driver._database = None  # reset driver
        self.driver.db_name = self.db_name

    def tearDown(self):
        LOG.debug("Deleting test mongodb: %s" % self.db_name)
        try:
            c = Connection()
            c.drop_database(self.db_name)
            LOG.debug("Deleted test mongodb: %s" % self.db_name)
        except Exception as exc:
            LOG.error("Error deleting test mongodb '%s': %s" % (self.db_name,
                                                                exc))

  
    @unittest.skipIf(SKIP, REASON)
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
        self.assertNotIn('_id', results, "Backend field '_id' should not be "
                         "exposed outside of driver")

        results = self.driver.get_components(with_secrets=False)
        self.assertEqual(len(results), 1)
        result = results.keys()[0]
        if isinstance(result, int):
            result = int(result)
        self.assertEqual(result, 1)
        self.assertDictEqual(results.values()[0], body)

    @unittest.skipIf(SKIP, REASON)
    def test_hex_id(self):
        id = uuid.uuid4().hex
        results = self.driver.save_component(id, dict(id=id), None,
                                             tenant_id='T1000')
        self.assertDictEqual(results, dict(id=id, tenantId='T1000'))
        self.assertNotIn('_id', results, "Backend field '_id' should not be "
                         "exposed outside of driver")

    @unittest.skipIf(SKIP, REASON)
    def test_no_id_in_body(self):
        id = uuid.uuid4().hex
        self.assertRaises(Exception, self.driver.save_component, id, {}, None,
                          tenant_id='T1000')

    @unittest.skipIf(SKIP, REASON)
    def test_multiple_objects(self):
        #Mongo returns all dictionaries in unicode - need to convert to UTF-8 to compare
        def _decode_dict(dictionary):
            decoded_dict = {}
            for key, value in dictionary.iteritems():
                if isinstance(key, unicode):
                    key = key.encode('utf-8')
                    if isinstance(key, int):
                        key = int(key)
                if isinstance(value, unicode):
                    value = value.encode('utf-8')
                    if isinstance(value, int):
                        value = int(value)
                elif isinstance (value, dict):
                    value = _decode_dict(value)
                decoded_dict[key] = value
            return decoded_dict
        
        expected = {}
        for i in range(1,5):
            print "ROUND: %s" % i
            expected[i] = dict(id=i, tenantId='T1000')
            print "expected: %s" % expected[i]
            body = self.driver.save_component(i, dict(id=i), None, tenant_id='T1000')
            print "body: %s" % body
        unicode_results = self.driver.get_components()
        results = _decode_dict(unicode_results)
        self.assertDictEqual(results, expected)
        for i in range(1,5):
            self.assertIn(i, results)
            self.assertNotIn('_id', results[i])
            self.assertEqual(results[i]['id'], i)

   


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
