# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import unittest

from checkmate.codegen import kwargs_from_string

class TestCodegen(unittest.TestCase):
    def test_build_kwargs_from_empty_string(self):
        func_name, kwargs = kwargs_from_string('')
        self.assertIsNone(func_name)
        self.assertEqual({}, kwargs)

    def test_attempt_kwargs_build_with_too_many_function_definitions(self):
        self.assertRaises(SyntaxError,
            kwargs_from_string, 'my_func(blah=2)\nmy_other_func()')

    def test_attempt_kwargs_build_with_nested_functions(self):
        self.assertRaises(ValueError,
            kwargs_from_string, 'my_func(my_other_func())')

    def test_build_kwargs_from_string_with_one_integer_value(self):
        func_name, kwargs = kwargs_from_string('my_func(blah=2)')
        self.assertEqual('my_func', func_name)
        self.assertEqual({'blah': 2}, kwargs)

    def test_build_kwargs_from_string_with_one_string_value(self):
        func_name, kwargs = kwargs_from_string("my_func(blah='blarg')")
        self.assertEqual('my_func', func_name)
        self.assertEqual({'blah': 'blarg'}, kwargs)

    def test_build_kwargs_from_string_with_one_array(self):
        func_name, kwargs = kwargs_from_string("my_func(blah=[1, '2', None])")
        self.assertEqual('my_func', func_name)
        self.assertEqual({'blah': [1, '2', None]}, kwargs)

    def test_build_kwargs_from_string_with_multiple_params(self):
        func_name, kwargs = kwargs_from_string(
            "my_func(blerg=8, blah=[1, '2', None], bleep='')")
        self.assertEqual('my_func', func_name)
        self.assertEqual({'blerg': 8, 'blah': [1, '2', None], 'bleep': ''}, kwargs)


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
