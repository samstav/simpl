# pylint: disable=C0103

# Copyright (c) 2011-2013 Rackspace Hosting
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Tests for DbBase class."""
import pickle
import unittest

from checkmate import db


class TestDbBase(unittest.TestCase):

    def test_instantiation(self):
        dbb = db.DbBase("connection-string://")
        self.assertEqual(dbb.connection_string, "connection-string://")

    def test_serialization(self):
        dbb = db.DbBase("connection-string://")
        self.assertEqual(str(dbb), "connection-string://")
        dbb2 = pickle.loads(pickle.dumps(dbb))
        self.assertEqual(dbb2.connection_string, "connection-string://")

    def test_representation(self):
        dbb = db.DbBase("connection-string://")
        self.assertEqual(repr(dbb), "<checkmate.db.base.DbBase "
                         "connection_string='connection-string://'>")

    def test_remove_string_secrets_success(self):
        """Verifies secrets removed from url."""
        url = 'mongodb://username:secret_pass@localhost:8080/checkmate'
        dbb = db.DbBase(url)
        expected = ("<checkmate.db.base.DbBase connection_string='mongodb://"
                    "username:*****@localhost:8080/checkmate'>")
        results = repr(dbb)
        self.assertEqual(expected, results)

    def test_remove_string_secrets_invalid_data(self):
        """Verifies data passed in is returned if not a basestring type."""
        url = 12345
        dbb = db.DbBase(url)
        results = repr(dbb)
        expected = "<checkmate.db.base.DbBase connection_string='12345'>"
        self.assertEqual(expected, results)

    def test_remove_string_secrets_used_in_repr(self):
        """Verifies secrets removed from repr."""
        url = 'mongodb://username:secret_pass@localhost:8080/checkmate'
        dbb = db.DbBase(url)
        expected = ("<checkmate.db.base.DbBase connection_string='mongodb://"
                    "username:*****@localhost:8080/checkmate'>")
        results = repr(dbb)
        self.assertEqual(expected, results)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
