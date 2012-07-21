#!/usr/bin/env python
import unittest2 as unittest

from checkmate.common import schema


class TestSchema(unittest.TestCase):
    def test_translation_exists(self):
        self.assertEqual(schema.translate('username'), 'username')

    def test_translation_alias(self):
        self.assertEqual(schema.translate('user'), 'username')

    def test_translation_unknown(self):
        self.assertEqual(schema.translate('foo'), None)

    def test_translation_edge_cases(self):
        self.assertEqual(schema.translate(None), None)
        self.assertEqual(schema.translate('/'), '/')
        self.assertEqual(schema.translate('.'), '_')

    def test_translation_composite(self):
        self.assertEqual(schema.translate('db_user'), 'database_username')
        self.assertEqual(schema.translate('db.user'), 'database_username')
        self.assertEqual(schema.translate('db-user'), 'database_username')

    def test_translation_path(self):
        self.assertEqual(schema.translate('db/user'), 'database/username')

    def test_translation_combined(self):
        self.assertEqual(schema.translate('dest.directory/pub_user'),
                'destination_directory/public_username')

if __name__ == '__main__':
    unittest.main()
