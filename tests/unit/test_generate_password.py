# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import string
import unittest

from checkmate import utils

DEFAULT_VALID_CHARS = ''.join([
    string.ascii_letters,
    string.digits
])


def as_set(chars):
    return set(''.join(chars))


class TestGeneratePassword(unittest.TestCase):
    def assertAllCharsAreValid(self, password, valid_chars):
        for char in password:
            self.assertTrue(
                char in valid_chars, "'%s' not in '%s'" % (char, valid_chars)
            )

    def assertAtLeastOne(self, password, required_chars):
        required_count = 0
        for char in password:
            if char in required_chars:
                required_count += 1
        self.assertFalse(
            required_count is 0,
            "'%s' does not contain any of '%s'" % (password, required_chars)
        )

    def test_generate_password_with_defaults(self):
        password = utils.generate_password()
        self.assertEqual(8, len(password))
        self.assertAllCharsAreValid(password, DEFAULT_VALID_CHARS)

    def test_generate_password_with_min_length(self):
        password = utils.generate_password(min_length=12)
        self.assertEqual(12, len(password))

    def test_generate_password_with_max_length(self):
        password = utils.generate_password(max_length=14)
        self.assertEqual(14, len(password))

    def test_generate_password_with_max_and_min_length(self):
        password = utils.generate_password(min_length=8, max_length=14)
        self.assertTrue(len(password) >= 8 and len(password) <= 14)

    def test_generate_password_with_valid_chars(self):
        password = utils.generate_password(
            starts_with=None, valid_chars='abc123')
        self.assertAllCharsAreValid(password, as_set('abc123'))

    def test_generate_password_with_starts_with(self):
        password = utils.generate_password(starts_with='abc123')
        self.assertTrue(password[0] in as_set('abc123'))

    def test_generate_password_with_one_required_chars_set(self):
        password = utils.generate_password(required_chars=['pqr!#34'])
        self.assertAtLeastOne(password, as_set('pqr!#34'))

    def test_generate_password_with_multiple_required_chars_sets(self):
        password = utils.generate_password(
            required_chars=['!@#', '$%^', '&*('])
        self.assertAtLeastOne(password, as_set('!@#'))
        self.assertAtLeastOne(password, as_set('$%^'))
        self.assertAtLeastOne(password, as_set('&*('))

    def test_required_chars_uses_total_password_length(self):
        password = utils.generate_password(
            min_length=3,
            starts_with=None,
            required_chars=['!@#', '$%^', '&*(']
        )
        self.assertAtLeastOne(password, as_set('!@#'))
        self.assertAtLeastOne(password, as_set('$%^'))
        self.assertAtLeastOne(password, as_set('&*('))

    def test_more_required_chars_than_password_length(self):
        with self.assertRaises(ValueError) as expected:
            utils.generate_password(
                min_length=2,
                starts_with=None,
                required_chars=['!@#', '$%^', '&*(']
            )
        self.assertEqual(
            'Password length is less than the number of required characters.',
            str(expected.exception)
        )

    def test_all_the_things(self):
        password = utils.generate_password(
            min_length=12,
            max_length=22,
            valid_chars='abcde12345!@#$%^&*(',
            starts_with='abcde',
            required_chars=['!@#', '$%^', '&*(']
        )
        self.assertTrue(12 <= len(password) <= 22)
        self.assertAllCharsAreValid(password, as_set('abcde12345!@#$%^&*('))
        self.assertAtLeastOne(password, as_set('!@#'))
        self.assertAtLeastOne(password, as_set('$%^'))
        self.assertAtLeastOne(password, as_set('&*('))

    def test_max_length_cannot_exceed_255(self):
        with self.assertRaises(ValueError) as expected:
            utils.generate_password(max_length=256)
        self.assertEqual(
            "Maximum password length of 255 characters exceeded.",
            str(expected.exception)
        )

    def test_min_length_cannot_exceed_255(self):
        with self.assertRaises(ValueError) as expected:
            utils.generate_password(min_length=256)
        self.assertEqual(
            "Maximum password length of 255 characters exceeded.",
            str(expected.exception)
        )
