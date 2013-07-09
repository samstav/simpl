# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import unittest

from checkmate.inputs import Input


class TestInput(unittest.TestCase):
    def test_init_method(self):
        self.assertIsInstance(Input({}), Input)

    def test_string_functionality(self):
        self.assertEquals(Input('test'), 'test')
        self.assertTrue(Input('test').startswith('t'))
        self.assertEqual(Input('A') + Input('B'), 'AB')

    def test_integer_functionality(self):
        self.assertEquals(Input('1'), '1')
        self.assertIsInstance(Input(1), int)
        self.assertEqual(Input('1') + Input('2'), '12')
        self.assertEqual(Input(1) + Input(2), 3)

    # pylint: disable=E1101
    def test_url_handling(self):
        data = {
            'url': 'http://example.com',
            'certificate': '----- BEGIN ....',
        }
        url = Input(data)
        self.assertEqual(url, 'http://example.com')

        self.assertTrue(hasattr(url, 'protocol'))
        self.assertEqual(url.protocol, 'http')

        self.assertTrue(hasattr(url, 'certificate'))
        self.assertEqual(url.certificate, '----- BEGIN ....')

    # pylint: disable=E1101
    def test_url_parsing(self):
        url = Input('https://example.com:80/path')
        url.parse_url()
        self.assertEqual(url, 'https://example.com:80/path')

        self.assertTrue(hasattr(url, 'protocol'))
        self.assertEqual(url.protocol, 'https')

        self.assertTrue(hasattr(url, 'scheme'))
        self.assertEqual(url.protocol, 'https')

        self.assertTrue(hasattr(url, 'netloc'))
        self.assertEqual(url.netloc, 'example.com:80')

        self.assertTrue(hasattr(url, 'hostname'))
        self.assertEqual(url.hostname, 'example.com')

    def test_attribute_availability(self):
        url = Input({})
        self.assertTrue(hasattr(url, 'url'))
        self.assertTrue(hasattr(url, 'certificate'))
        self.assertTrue(hasattr(url, 'private_key'))
        self.assertTrue(hasattr(url, 'intermediate_key'))

    # pylint: disable=E1101
    def test_non_standard_urls(self):
        url = Input('git://github.com')
        url.parse_url()
        self.assertTrue(hasattr(url, 'url'))
        self.assertEqual(url.url, 'git://github.com')

        self.assertTrue(hasattr(url, 'protocol'))
        self.assertEqual(url.protocol, 'git')


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
