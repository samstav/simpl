#!/usr/bin/env python
import json
import os
from SpiffWorkflow.specs import Celery
from SpiffWorkflow.storage import DictionarySerializer
from string import Template
import sys
import unittest2 as unittest
import yaml

os.environ['CHECKMATE_DATA_PATH'] = os.path.join(os.path.dirname(__file__),
                                              'data')
os.environ['BROKER_USERNAME'] = os.environ.get('BROKER_USERNAME', 'checkmate')
os.environ['BROKER_PASSWORD'] = os.environ.get('BROKER_PASSWORD', 'password')
os.environ['BROKER_HOST'] = os.environ.get('BROKER_HOST', 'localhost')
os.environ['BROKER_PORT'] = os.environ.get('BROKER_PORT', '5672')

from checkmate import server
from checkmate.deployments import plan_dict
from checkmate.workflows import create_workflow
from checkmate.utils import resolve_yaml_external_refs


class TestWorkflow(unittest.TestCase):
    """ Test Basic Server code """

    @classmethod
    def setUpClass(cls):
        # Load app.yaml, substitute variables
        path = os.path.join(os.path.dirname(__file__), '..', 'examples',
            'app.yaml')
        with file(path) as f:
            source = f.read().decode('utf-8')
        env = {
                'CHECKMATE_USERNAME': '1',
                'CHECKMATE_APIKEY': '2',
                'CHECKMATE_PUBLIC_KEY': '3',
                'CHECKMATE_PRIVATE_KEY': '4',
                'CHECKMATE_DOMAIN': '5',
                'CHECKMATE_REGION': '6'
            }
        t = Template(source)
        env.update(os.environ)
        parsed = t.safe_substitute(**env)
        app = yaml.safe_load(yaml.emit(resolve_yaml_external_refs(parsed),
                         Dumper=yaml.SafeDumper))
        deployment = app['deployment']
        deployment['id'] = 'abcdefghijklmnopqrstuvwxyz'
        cls.deployment = deployment

    def setUp(self):
        # Parse app.yaml as a deployment
        result = plan_dict(TestWorkflow.deployment)
        self.deployment = result['deployment']
        self.workflow = result['workflow']

    def test_workflow_completion(self):
        responses = {
            'Authenticate': {'token': "got_a_token"},
            'Write Token to Deployment': None
            }

        def hijacked_try_fire(self, my_task, force=False):
            """We patch this in to intercept calls that would go to celery"""
            celery_module = sys.modules['SpiffWorkflow.specs.Celery']
            if self.args:
                args = celery_module.eval_args(self.args, my_task)
                if self.kwargs:
                    print "Hijacked %s(%s, %s)" % (self.call, args,
                            celery_module.eval_kwargs(self.kwargs, my_task))
                else:
                    print "Hijacked %s(%s)" % (self.call, args)
            else:
                if self.kwargs:
                    print "Hijacked %s(%s, %s)" % (self.call,
                            celery_module.eval_kwargs(self.kwargs, my_task))
                else:
                    print "Hijacked %s(%s, %s)" % (self.call)
            name = my_task.get_name()
            response = None
            if name in responses:
                if responses[name]:
                    response = responses[name]
            elif name.startswith('Create Server'):
                i = name.split(":")[1]
                response = {'id': 1000 + int(i), 'ip': "10.1.1.%s" % i,
                        'password': 'shecret'}
            elif name.startswith('Create LB'):
                i = name.split(":")[1]
                response = {'id': 2000 + int(i), 'vip': "200.1.1.%s" % i}
            elif name.startswith('Create DB'):
                i = name.split(":")[1]
                response = {'id': 1000 + int(i), 'name': 'dbname.domain.local',
                        'status': 'BUILD', 'hostname':
                        'verylong.rackclouddb.com'}
            elif name.startswith('Add DB User'):
                i = name.split(":")[1]
                response = {'id': 1000 + int(i), 'ip': "10.1.1.%s" % i,
                        'password': 'shecret'}
            else:
                print "Unhandled: %s" % name
            if response:
                my_task.set_attribute(**response)
            return True
        try_fire = Celery.try_fire
        try:
            Celery.try_fire = hijacked_try_fire
            self.workflow.complete_all()
            self.assertTrue(self.workflow.is_completed())
        finally:
            Celery.try_fire = try_fire
        serializer = DictionarySerializer()
        print json.dumps(self.workflow.serialize(serializer), indent=2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
