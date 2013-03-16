""" tests for schema.py """
import unittest2 as unittest

from checkmate.common import schema

#Commented out test correspond to removal of '.-_' translations


class TestSchema(unittest.TestCase):
    """ Test various schema related functions """

    def test_translation_apache(self):
        self.assertEqual(schema.translate('apache2'), 'apache')

    def test_translation_exists(self):
        self.assertEqual(schema.translate('username'), 'username')

    def test_translation_alias(self):
        self.assertEqual(schema.translate('db'), 'database')

    def test_translation_unknown(self):
        self.assertEqual(schema.translate('foo'), 'foo')

    def test_translation_edge_cases(self):
        self.assertEqual(schema.translate(None), None)
        self.assertEqual(schema.translate('/'), '/')
        #self.assertEqual(schema.translate('.'), '_')

#    def test_translation_composite(self):
#        self.assertEqual(schema.translate('db_hostname'), 'database_host')
#        self.assertEqual(schema.translate('db.hostname'), 'database_host')
#        self.assertEqual(schema.translate('db-hostname'), 'database_host')

    def test_validate(self):
        errors = schema.validate(
            {
                "label": "foo",
            },
            schema.OPTION_SCHEMA)
        self.assertEqual([], errors)

    def test_validate_negative(self):
        errors = schema.validate(
            {
                "name": "deprecated",
            },
            schema.OPTION_SCHEMA)
        self.assertEqual(len(errors), 1)

    def test_validate_option(self):
        errors = schema.validate_option("any",
            {
                "label": "foo",
                "type": "string",
                "default": "None",
                "display-hints": {
                    "group": "test group",
                    "weight": 5
                },
                'help': "Here's how...",
                'sample': "foo",
                'choice': [],
                'description': "Yada yada",
                'required': False,
                'type': "string",
                'constrains': [],
                'constraints': [],
                'display-hints': {},
            })
        self.assertEqual([], errors)

    def test_validate_option_negative(self):
        errors = schema.validate_option("key",
            {
                "name": "deprecated",
                "type": "foo",
            })
        self.assertEqual(len(errors), 2, msg=errors)

    def test_translation_path(self):
        self.assertEqual(schema.translate('db/hostname'), 'database/host')

#    def test_translation_combined(self):
#        self.assertEqual(schema.translate('dest.directory/pub_conf'),
#                'destination_directory/public_configuration')

if __name__ == '__main__':
    unittest.main()
