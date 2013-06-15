import checkmate.db.mongodb
import unittest2 as unittest


class TestMongoDB(unittest.TestCase):
    def _check(self, field, result):
        self.assertEqual(checkmate.db.mongodb.parse_comparison(field), result)

    def test_comparison_equal(self):
        self._check("FOO", "FOO")

    def test_comparison_not_equal(self):
        self._check("!FOO", {'$ne': "FOO"})

    def test_comparison_greater_than(self):
        self._check(">FOO", {'$gt': "FOO"})

    def test_comparison_greater_than_equal(self):
        self._check(">=FOO", {'$gte': "FOO"})

    def test_comparison_less_than(self):
        self._check("<FOO", {'$lt': "FOO"})

    def test_comparison_less_than_equal(self):
        self._check("<=FOO", {'$lte': "FOO"})
