from checkmate.deployment import Deployment
import unittest

from checkmate.deployments import Plan


class TestPlan(unittest.TestCase):
    def test_add_resource(self):
        plan = Plan(Deployment({'blueprint': {'services': {}}}))
        plan.resource_index = 0
        resource = {}
        definition = {}
        plan.add_resource(resource, definition)

        self.assertEqual(len(definition["instances"]), 1)
        self.assertEqual(definition["instances"][0], '0')
        self.assertEqual(len(plan.resources), 1)
        self.assertEqual(plan.resources['0'], resource)

    def test_add_resource_and_update_connections_for_vip(self):
        plan = Plan(Deployment({'blueprint': {
            'services': {'lb': {'component': {'interface': 'vip'}}}}}))
        plan.resource_index = 0
        resource = {}
        definition = {'connections': {'master': {}, 'web': {}}}
        plan.add_resource(resource, definition, 'lb')
        master = bool(definition['connections']['master'].get('outbound-from'))
        web = bool(definition['connections']['web'].get('outbound-from'))
        self.assertTrue(master != web)
        if master:
            self.assertEqual(
                definition['connections']['master']['outbound-from'], '0')
        if web:
            self.assertEqual(
                definition['connections']['web']['outbound-from'], '0')


if __name__ == '__main__':
    # Run tests. Handle our parameters separately
    import sys

    args = sys.argv[:]
    # Our --debug means --verbose for unittest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
