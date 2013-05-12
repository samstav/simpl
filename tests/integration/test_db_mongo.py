# pylint: disable=R0904,C0103
'''
Test MongoDB using MongoBox
'''
import sys

try:
    from mongobox import MongoBox
    SKIP = False
    REASON = None
except ImportError as exc:
    SKIP = True
    REASON = "'mongobox' not installed: %s" % exc
    MongoBox = object
import unittest2 as unittest

import base  # pylint: disable=W0403


TEST_MONGO_INSTANCE = ('mongodb://checkmate:%s@mongo-n01.dev.chkmate.rackspace'
                       '.net:27017/checkmate' % 'c%40m3yt1ttttt')


@unittest.skipIf(SKIP, REASON)
class TestDBMongo(base.DBDriverTests):
    '''MongoDB Driver Canned Tests'''

    #pylint: disable=W0603
    @classmethod
    def setUpClass(cls):
        '''Fire up a sandboxed mongodb instance'''
        super(TestDBMongo, cls).setUpClass()
        try:
            cls.box = MongoBox()
            cls.box.start()
            cls.connection_string = ("mongodb://localhost:%s/test" %
                                     cls.box.port)
        except StandardError as exc:
            if hasattr(cls, 'box'):
                del cls.box
            # Hate to do it, but until we get jenkins sorted this hacks us thru
            cls.connection_string = TEST_MONGO_INSTANCE
            return
            global SKIP
            global REASON
            SKIP = True
            REASON = str(exc)

    @classmethod
    def tearDownClass(cls):
        '''Stop the sanboxed mongodb instance'''
        if hasattr(cls, 'box') and isinstance(cls.box, MongoBox):
            if cls.box.running() is True:
                cls.box.stop()
                cls.box = None
        super(TestDBMongo, cls).tearDownClass()


@unittest.skipIf(SKIP, REASON)
class TestMongoDBCapabilities(unittest.TestCase):
    '''Test MongoDB's capabilities against our driver design

    We do things like document partial updates and locking with mongodb. The
    way we do that might break with certain versions of Mongo, so this test
    module validates that our designs work as expected.

    These tests are optional. If MongoDB is not installed, they will be
    skipped.

    '''
    #pylint: disable=W0603
    @classmethod
    def setUpClass(cls):
        '''Fire up a sandboxed mongodb instance'''
        try:
            cls.box = MongoBox()
            cls.box.start()
        except StandardError as exc:
            if hasattr(cls, 'box'):
                del cls.box
            # Hate to do it, but until we get jenkins sorted this hacks us thru
            cls.connection_string = TEST_MONGO_INSTANCE
            global SKIP
            global REASON
            SKIP = True
            REASON = str(exc)

    @classmethod
    def tearDownClass(cls):
        '''Stop the sanboxed mongodb instance'''
        if hasattr(cls, 'box') and isinstance(cls.box, MongoBox):
            if cls.box.running() is True:
                cls.box.stop()
                cls.box = None

    def setUp(self):
        '''Get a client conection to our sandboxed mongodb instance'''
        if hasattr(self, 'box'):
            self.client = self.box.client()
        else:
            raise unittest.SkipTest("No sandboxed mongoDB")

    def tearDown(self):
        '''Disconnect the client'''
        if hasattr(self, 'box'):
            self.client = None

    def test_mongo_instance(self):
        '''Verify the mongobox's mongodb instance is working'''
        self.assertTrue(self.client.alive())

    def test_mongo_object_creation(self):
        '''Verify object creation'''
        col = self.client.tdb.c1
        col.save({})
        self.assertIn('tdb', self.client.database_names())
        self.assertIn('c1', self.client.tdb.collection_names())
        self.assertEqual(1, col.count())

    def test_mongo_custom_id(self):
        '''Verify assigning IDs'''
        col = self.client.tdb.c2
        col.save({'id': 'our-id'})
        result = col.find_one({'id': 'our-id'})
        self.assertIn('id', result, msg="Our ID was not returned")
        self.assertIn('_id', result, msg="Mongo no longer has an _id field")
        self.assertEqual(len(result), 2, msg="Mongo added unexpected fields")
        self.assertNotEqual(result['id'], result['_id'],
                            msg="Mongo's and our IDs are now the same")
        self.assertEqual(result['id'], 'our-id', msg="Our ID is not intact")

    def test_mongo_projection(self):
        '''We can return our IDs with only specific fields'''
        col = self.client.tdb.c3
        col.save({'id': 'our-id', 'name': 'Ziad', 'hide': 'X'})
        result = col.find_one(
            {'id': 'our-id'},
            {
                '_id': 0,
                'hide': 0
            }
        )
        self.assertDictEqual(result, {'id': 'our-id', 'name': 'Ziad'})

    def test_partial_update(self):
        '''We can update only specific fields'''
        col = self.client.tdb.c4
        col.save({'id': 'our-id', 'status': 'PLANNED', 'name': 'Ziad'})
        obj = col.find_one({'id': 'our-id'}, {'_id': 0})
        self.assertIn('name', obj, msg="'name' was not saved")

        col.update(
            {'id': 'our-id'},
            {
                '$set': {
                    'status': 'UP'
                }
            }
        )
        obj = col.find_one({'id': 'our-id'}, {'_id': 0})
        self.assertIn('name', obj, msg="'name' was removed by an update")
        self.assertDictEqual(obj, {'id': 'our-id', 'status': 'UP',
                                   'name': 'Ziad'})

    def test_deep_partial_update_unsupported(self):
        '''Mongo update is like a dict.update() - it overwrites whole keys'''
        col = self.client.tdb.c5
        col.save(
            {
                'id': 'our-id',
                'status': 'PLANNED',
                'subobj': {
                    'name': 'Ziad',
                    'status': 'busy',
                }
            }
        )

        col.update(
            {'id': 'our-id'},
            {
                '$set': {
                    'status': 'UP',
                    'subobj': {
                        'status': 'gone fishing'
                    }
                }
            }
        )
        obj = col.find_one({'id': 'our-id'}, {'_id': 0})
        self.assertIn('id', obj, msg="'id' was removed by an update")
        self.assertIn('subobj', obj, msg="'subobj' was removed by an update")
        subobj = obj['subobj']
        self.assertNotIn('name', subobj, msg="Writing partials now works!!!")
        self.assertDictEqual(obj, {
            'id': 'our-id',
            'status': 'UP',
            'subobj': {
                'status': 'gone fishing'
            }
        })

    def test_write_if_zero(self):
        '''Verify that syntax for locking an object works'''
        col = self.client.tdb.c6
        col.save(
            {
                'id': 'our-id',
                '_lock': 0
            }
        )
        obj = col.find_and_modify(
            query={
                '$or': [{'_lock': {'$exists': False}}, {'_lock': 0}]
            },
            update={
                '$set': {
                    '_lock': "1",
                }
            },
            fields={'_lock': 0, '_id': 0}
        )
        self.assertEqual(obj['id'], 'our-id')

    def test_write_if_field_not_exists(self):
        '''Verify that syntax for locking an object works'''
        col = self.client.tdb.c7
        col.save(
            {
                'id': 'our-id',
            }
        )
        obj = col.find_and_modify(
            query={
                '$or': [{'_lock': {'$exists': False}}, {'_lock': 0}]
            },
            update={
                '$set': {
                    '_lock': "1",
                }
            },
            fields={'_lock': 0, '_id': 0}
        )
        self.assertEqual(obj['id'], 'our-id')

    def test_skip_if_filtered(self):
        '''Verify that syntax for locking an object works'''
        col = self.client.tdb.c8
        col.save(
            {
                'id': 'our-id',
                '_lock': 'my-key'
            }
        )
        obj = col.find_and_modify(
            query={
                '$or': [{'_lock': {'$exists': False}}, {'_lock': 0}]
            },
            update={
                '$set': {
                    '_lock': "1",
                }
            },
            fields={'_lock': 0, '_id': 0}
        )
        self.assertIsNone(obj)


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
