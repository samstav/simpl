# pylint: disable=C0103,E1101,E1103,R0201,R0903,R0904,W0201,W0212,W0232
"""Tests for DbBase class."""
import pickle
import unittest

from checkmate import db


class TestDbBase(unittest.TestCase):

    def test_instantiation(self):
        dbb = db.DbBase("connection-string://")
        self.assertEquals(dbb.connection_string, "connection-string://")

    def test_serialization(self):
        dbb = db.DbBase("connection-string://")
        self.assertEqual(str(dbb), "connection-string://")
        self.assertEqual(repr(dbb), "<checkmate.db.base.DbBase "
                         "connection_string='connection-string://'>")
        dbb2 = pickle.loads(pickle.dumps(dbb))
        self.assertEqual(dbb2.connection_string, "connection-string://")

    def test_convert_data_status(self):
        dbb = db.DbBase("connection-string://")
        data = {
            'status': 'BUILD',
        }
        expected = {
            'status': 'UP',
        }
        dbb.convert_data('deployments', data)
        self.assertEqual(data, expected)

    def test_convert_data_messages(self):
        dbb = db.DbBase("connection-string://")
        data = {
            "1": {
                'statusmsg': '',
                'instance': {
                    'statusmsg': '',
                }
            }
        }
        expected = {
            "1": {
                'status-message': '',
                'instance': {
                    'status-message': '',
                }
            }
        }
        dbb.convert_data('resources', data)
        self.assertEqual(data, expected)

    def test_convert_data_display_messages(self):
        dbb = db.DbBase("connection-string://")
        data = {
            'display-outputs': None
        }
        expected = {
            'display-outputs': {}
        }
        dbb.convert_data('deployments', data)
        self.assertEqual(data, expected)

    def test_convert_data_error(self):
        dbb = db.DbBase("connection-string://")
        data = {
            "1": {
                'errmessage': 'my error message',
                'error-traceback': 'some trace',
                'instance': {
                    'trace': ''
                }
            }
        }
        expected = {
            "1": {
                'instance': {
                    'error-message': 'my error message',
                }
            }
        }
        dbb.convert_data('resources', data)
        self.assertEqual(data, expected)

    def test_convert_data_del_errmessage(self):
        dbb = db.DbBase("connection-string://")
        data = {
            "1": {
                'errmessage': '',
                'instance': {
                    'errmessage': '',
                    'error-message': 'my error message'
                }
            }
        }
        expected = {
            "1": {
                'instance': {
                    'error-message': 'my error message'
                }
            }
        }
        dbb.convert_data('resources', data)
        self.assertEqual(data, expected)

    def test_remove_string_secrets_success(self):
        """Verifies secrets removed from url."""
        url = 'mongodb://username:secret_pass@localhost:8080/checkmate'
        dbb = db.DbBase(url)
        expected = 'mongodb://username@localhost:8080/checkmate'
        results = dbb.remove_string_secrets(url)
        self.assertEqual(expected, results)

    def test_remove_string_secrets_invalid_data(self):
        """Verifies data passed in is returned if not a basestring type."""
        url = 12345
        dbb = db.DbBase("connection-string://")
        results = dbb.remove_string_secrets(url)
        self.assertEqual(url, results)

if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
