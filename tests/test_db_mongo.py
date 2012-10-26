#!/usr/bin/env python
import logging
import os
import unittest2 as unittest
import uuid

from pymongo import Connection, uri_parser
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

tester = { 'some': 'random',
               'tenantId': 'T100',
               'id' : 1 }

class TestDatabase(unittest.TestCase):
    """ Test Mongo Database code """
    
    def setUp(self):
        self.collection_name = 'checkmate_test_%s' % uuid.uuid4().hex
        self.driver = db.get_driver('checkmate.db.mongodb.Driver', True)
        print self.driver.__class__
        self.driver.DB = None
        self.driver.connection_string = 'mongodb://checkmate:%s@mongo-n01.dev.chkmate.rackspace.net:27017/checkmate' % ('c%40m3yt1ttttt',)
        #self.connection_string = 'localhost'
        self.driver._connection = self.driver._database = None  # reset driver
        self.driver.db_name = 'checkmate'

    
    def tearDown(self):
        LOG.debug("Deleting test mongodb collection: %s" % self.collection_name)
        try:
            connection_string = 'mongodb://checkmate:%s@mongo-n01.dev.chkmate.rackspace.net:27017/checkmate' % ('c%40m3yt1ttttt', )
            #connection_string = 'localhost'
            c = Connection(connection_string)
            db = c.checkmate
            collection_name = self.collection_name
            db.collection_name.drop()
            LOG.debug("Deleted test mongodb collection: %s" % self.collection_name)
        except Exception as exc:
            LOG.error("Error deleting test mongodb collection '%s': %s" % (self.collection_name,))

  
    @unittest.skipIf(SKIP, REASON)
    def test_objects(self):

        def _decode_dict(dictionary):
            decoded_dict = {}
            for key, value in dictionary.iteritems():
                if isinstance(key, unicode):
                    key = key.encode('utf-8')
                if isinstance(value, unicode):
                    value = value.encode('utf-8')
                    if isinstance(value, int):
                        value = int(value)
                elif isinstance (value, dict):
                    value = _decode_dict(value)
                decoded_dict[key] = value
            return decoded_dict

        entity = {'id': 1,
                  'name': 'My Component',
                  'credentials': ['My Secrets']
                  }
        body, secrets = extract_sensitive_data(entity)
        results = self.driver.save_object(self.collection_name, entity['id'], body, secrets,
                                             tenant_id='T1000')
        self.assertDictEqual(results, body)

        results = self.driver.get_object(self.collection_name, entity['id'], with_secrets=True)
        entity['tenantId'] = 'T1000'  # gets added
        self.assertDictEqual(results, entity)
        self.assertIn('credentials', results)

        body['name'] = 'My Updated Component'
        entity['name'] = 'My Updated Component'
        results = self.driver.save_object(self.collection_name, entity['id'], body, secrets)
        results = self.driver.get_object(self.collection_name, entity['id'], with_secrets=True)
        self.assertIn('credentials', results)
        self.assertDictEqual(results, entity)

        results = self.driver.get_object(self.collection_name, entity['id'], with_secrets=False)
        self.assertNotIn('credentials', results)
        body['tenantId'] = 'T1000'  # gets added
        self.assertDictEqual(results, body)
        self.assertNotIn('_id', results, "Backend field '_id' should not be "
                         "exposed outside of driver")

        results = self.driver.get_objects(self.collection_name, with_secrets=False)
        wrapper = {} # Needed to test for length of a result with only one returned value
        wrapper ['results'] = results
        self.assertEqual(len(wrapper), 1)

        results = _decode_dict(results)
	self.assertIn('id', results)
        self.assertEqual(results['id'], 1)
        self.assertDictEqual(results, body)

    @unittest.skipIf(SKIP, REASON)
    def test_hex_id(self):
        def _decode_dict(dictionary):
            decoded_dict = {}
            for key, value in dictionary.iteritems():
                if isinstance(key, unicode):
                    key = key.encode('utf-8')
                if isinstance(value, unicode):
                    value = value.encode('utf-8')
                    if isinstance(value, int):
                        value = int(value)
                elif isinstance (value, dict):
                    value = _decode_dict(value)
                decoded_dict[key] = value
            return decoded_dict
        id = uuid.uuid4().hex
        body = self.driver.save_object(self.collection_name, id, dict(id=id), None,
                                             tenant_id='T1000')
        unicode_results = self.driver.get_objects(self.collection_name)
        results = _decode_dict(unicode_results)
        self.assertDictEqual(results, dict(id=id, tenantId='T1000'))
        self.assertNotIn('_id', results, "Backend field '_id' should not be "
                         "exposed outside of driver")

    @unittest.skipIf(SKIP, REASON)
    def test_no_id_in_body(self):
        id = uuid.uuid4().hex
        self.assertRaises(Exception, self.driver.save_object, id, {}, None,
                          tenant_id='T1000')

    @unittest.skipIf(SKIP, REASON)
    def test_multiple_objects(self):
        #Mongo returns all dictionaries in unicode - need to convert to UTF-8 to compare
        def _decode_dict(dictionary):
            decoded_dict = {}
            for key, value in dictionary.iteritems():
                if isinstance(key, unicode):
                    key = key.encode('utf-8')
                    try:
                        key = int(key)
                    except Exception:
                        key = key
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
            expected[i] = dict(id=i, tenantId='T1000')
            body = self.driver.save_object(self.collection_name, i, dict(id=i), None, tenant_id='T1000')
        unicode_results = self.driver.get_objects(self.collection_name)
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
