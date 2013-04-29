# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method '''

import pickle
import unittest2 as unittest

from checkmate.db import DbBase


class TestDbBase(unittest.TestCase):

    def test_instantiation(self):
        dbb = DbBase("connection-string://")
        self.assertEquals(dbb.connection_string, "connection-string://")

    def test_serialization(self):
        dbb = DbBase("connection-string://")
        self.assertEqual(str(dbb), "connection-string://")
        self.assertEqual(repr(dbb), "<checkmate.db.base.DbBase "
                         "connection_string='connection-string://'>")
        dbb2 = pickle.loads(pickle.dumps(dbb))
        self.assertEqual(dbb2.connection_string, "connection-string://")


if __name__ == '__main__':
    unittest.main()
