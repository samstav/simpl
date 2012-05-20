import logging
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
