import logging
import random
import string

import clouddb
from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.specs import Celery

from checkmate.providers import ProviderBase


LOG = logging.getLogger(__name__)


class Provider(ProviderBase):
    def generate_template(self, deployment, service_name, service, name=None):
        inputs = deployment.get('inputs', {})

        flavor = inputs.get('%s:instance/flavor' % service_name,
                    service['config']['settings'].get(
                            '%s:instance/flavor' % service_name,
                            service['config']['settings']
                                    ['instance/flavor']['default']))

        if not name:
            name = 'CMDEP%s-db.rackclouddb.com' % (deployment['id'][0:7])
        template = {'type': 'database', 'dns-name': name,
                                     'flavor': flavor, 'instance-id': None}

        return template

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
            wait_on=None):
        start_with = string.ascii_uppercase + string.ascii_lowercase
        password = '%s%s' % (random.choice(start_with),
                ''.join(random.choice(start_with + string.digits + '@?#_')
                for x in range(11)))
        db_name = 'db1'
        username = 'wp_user_%s' % db_name

        create_db_task = Celery(wfspec, 'Create DB',
                               'stockton.db.distribute_create_instance',
                               call_args=[Attrib('context'),
                                        resource.get('dns-name'), 1,
                                        resource.get('flavor', 1),
                                        [{'name': db_name}]],
                               update_chef=True,
                               defines={"Resource": key},
                               properties={'estimated_duration': 80})
        create_db_user = Celery(wfspec, "Add DB User:%s" % username,
                               'stockton.db.distribute_add_user',
                               call_args=[Attrib('context'),
                                        Attrib('id'), [db_name],
                                        username, password],
                               properties={'estimated_duration': 20})
        # Store these in the context for use by other tasks
        context['db_name'] = db_name
        context['db_username'] = username
        context['db_password'] = password
        create_db_task.connect(create_db_user)
        return {'root': create_db_task, 'final': create_db_user}

    def get_catalog(self, context, type_filter=None):
        api = self._connect(context)
        results = {}

        if type_filter is None or type_filter == 'regions':
            regions = {}
            for service in context.catalog:
                if service['type'] == 'rax:database':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        if 'region' in endpoint:
                            regions[endpoint['region']] = endpoint['publicURL']
            results['regions'] = regions

        if type_filter is None or type_filter == 'size':
            flavors = api.flavors.list_flavors()
            results['sizes'] = {
                f.id: {
                    'name': f.name,
                    } for f in flavors}

        return results

    def _connect(self, context):
        """Use context info to connect to API and return api object"""
        #FIXME: handle region in context
        if not context.auth_tok:
            raise CheckmateNoTokenError()

        def find_url(catalog):
            for service in catalog:
                if service['type'] == 'rax:database':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        return endpoint['publicURL']

        def find_a_region(catalog):
            for service in catalog:
                if service['type'] == 'rax:database':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        return endpoint['region']

        api = clouddb.CloudDB(context.user, 'dummy',
                find_a_region(context.catalog) or 'DFW')
        api.client.auth_token = context.auth_tok
        url = find_url(context.catalog)
        api.client.region_account_url = url

        return api
