# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method '''

import unittest2 as unittest

from checkmate.common import schema
from checkmate.common.fysom import Fysom
from checkmate import utils


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
                                            'choice': [],
                                            'description': "Yada yada",
                                            'required': False,
                                            'constrains': [],
                                            'constraints': [],
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

    def test_validate_inputs(self):
        """Test that known input formats all pass validation"""
        deployment = utils.yaml_to_dict("""
            blueprint:
              options:
                my_simple_url:
                  type: url
                my_complex_url:
                  type: url
                my_int:
                  type: integer
                my_boolean:
                  type: boolean
                my_string:
                  type: string
            inputs:
              blueprint:
                my_simple_url: http://domain.com
                my_complex_url:
                  url: https://secure.domain.com
                  certificate: |
                    ----- BEGIN ....
                my_int: 1
                my_boolean: true
                my_string: Hello!
            """)
        self.assertListEqual(schema.validate_inputs(deployment), [])

    def test_validate_inputs_url_negative(self):
        """Test that bad url input formats don't pass validation"""
        deployment = utils.yaml_to_dict("""
            blueprint:
              options:
                try_list:
                  type: url
                bad_fields:
                  type: url
                try_int:
                  type: url
                try_boolean:
                  type: url
            inputs:
              blueprint:
                try_list:
                - url: http://domain.com
                - certificate: blah
                bad_fields:
                  foo: https://secure.domain.com
                  bar: |
                    ----- BEGIN ....
                try_int: 1
                try_boolean: true
            """)
        expected = [
            ("'foo' not a valid value. Only url, protocol, scheme, netloc, "
             "hostname, port, path, certificate, private_key, "
             "intermediate_key allowed"),
            ("'bar' not a valid value. Only url, protocol, scheme, netloc, "
             "hostname, port, path, certificate, private_key, "
             "intermediate_key allowed"),
            ("Option 'try_list' should be a string or valid url mapping. It "
             "is a 'list' which is not valid"),
            ("Option 'try_int' should be a string or valid url mapping. It is "
             "a 'int' which is not valid"),
            ("Option 'try_boolean' should be a string or valid url mapping. "
             "It is a 'bool' which is not valid"),
        ]
        results = schema.validate_inputs(deployment)
        results.sort()
        expected.sort()
        self.assertListEqual(results, expected)


#pylint: disable=E1101
class TestStateMachine(unittest.TestCase):
    def test_get_state_events_none(self):
        self.assertListEqual(schema.get_state_events(None), [])

    def test_get_state_events_no_events(self):
        data = {'TEST': {'description': 'No events'}}
        self.assertListEqual(schema.get_state_events(data), [])

    def test_get_state_events(self):
        data = {
            'START': {
                'events': [{'a': 1}, {'a': 2}]
            },
            'END': {
                'events': [{'b': 1}, {'b': 2}]
            },
        }
        expected = [
            {'a': 1, 'src': 'START'},
            {'a': 2, 'src': 'START'},
            {'b': 1, 'src': 'END'},
            {'b': 2, 'src': 'END'},
        ]
        self.assertListEqual(schema.get_state_events(data), expected)

    def test_deployment_states_fail_to_plan(self):
        fsm = Fysom({
            'initial': 'NEW',
            'events': schema.get_state_events(schema.DEPLOYMENT_STATUSES),
        })
        self.assertEquals(fsm.current, 'NEW')

        fsm.fail()
        self.assertEquals(fsm.current, 'FAILED')

        fsm.delete()
        self.assertEquals(fsm.current, 'DELETED')

    def test_deployment_states_fail_to_build(self):
        fsm = Fysom({
            'initial': 'NEW',
            'events': schema.get_state_events(schema.DEPLOYMENT_STATUSES),
        })
        self.assertEquals(fsm.current, 'NEW')

        fsm.plan()
        self.assertEquals(fsm.current, 'PLANNED')

        fsm.fail()
        self.assertEquals(fsm.current, 'FAILED')

    def test_deployment_states_build(self):
        fsm = Fysom({
            'initial': 'PLANNED',
            'events': schema.get_state_events(schema.DEPLOYMENT_STATUSES),
        })
        self.assertEquals(fsm.current, 'PLANNED')

        fsm.deploy()
        self.assertEquals(fsm.current, 'UP')

    def test_deployment_states_alert_and_fix(self):
        fsm = Fysom({
            'initial': 'UP',
            'events': schema.get_state_events(schema.DEPLOYMENT_STATUSES),
        })
        self.assertEquals(fsm.current, 'UP')

        fsm.alert()
        self.assertEquals(fsm.current, 'ALERT')

        fsm.fix()
        self.assertEquals(fsm.current, 'UP')

    def test_deployment_states_reconnect(self):
        fsm = Fysom({
            'initial': 'UP',
            'events': schema.get_state_events(schema.DEPLOYMENT_STATUSES),
        })
        self.assertEquals(fsm.current, 'UP')

        fsm.cannot_connect()
        self.assertEquals(fsm.current, 'NON-RESPONSIVE')

        fsm.reconnect()
        self.assertEquals(fsm.current, 'UP')

    def test_deployment_states_reconnect_to_alert(self):
        fsm = Fysom({
            'initial': 'NON-RESPONSIVE',
            'events': schema.get_state_events(schema.DEPLOYMENT_STATUSES),
        })
        self.assertEquals(fsm.current, 'NON-RESPONSIVE')

        fsm.alert()
        self.assertEquals(fsm.current, 'ALERT')

    def test_deployment_states_reconnect_to_down(self):
        fsm = Fysom({
            'initial': 'NON-RESPONSIVE',
            'events': schema.get_state_events(schema.DEPLOYMENT_STATUSES),
        })
        self.assertEquals(fsm.current, 'NON-RESPONSIVE')

        fsm.down()
        self.assertEquals(fsm.current, 'DOWN')

    def test_deployment_states_up_down(self):
        fsm = Fysom({
            'initial': 'UP',
            'events': schema.get_state_events(schema.DEPLOYMENT_STATUSES),
        })
        self.assertEquals(fsm.current, 'UP')

        fsm.down()
        self.assertEquals(fsm.current, 'DOWN')

        fsm.fix()
        self.assertEquals(fsm.current, 'UP')

    def test_deployment_states_delete_broken(self):
        fsm = Fysom({
            'initial': 'DOWN',
            'events': schema.get_state_events(schema.DEPLOYMENT_STATUSES),
        })
        self.assertEquals(fsm.current, 'DOWN')

        fsm.delete()
        self.assertEquals(fsm.current, 'DELETED')

    def test_deployment_states_delete(self):
        fsm = Fysom({
            'initial': 'UP',
            'events': schema.get_state_events(schema.DEPLOYMENT_STATUSES),
        })
        self.assertEquals(fsm.current, 'UP')

        fsm.delete()
        self.assertEquals(fsm.current, 'DELETED')


if __name__ == '__main__':
    # Any change here should be made in all test files
    import os, sys
    sys.path.insert(1, os.path.join(sys.path[0], '../..'))
    from tests.utils import run_with_params
    run_with_params(sys.argv[:])
