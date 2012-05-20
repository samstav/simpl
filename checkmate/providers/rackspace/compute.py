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
        image = inputs.get('%s:instance/os' % service_name,
                service['config']['settings'].get(
                        '%s:instance/os' % service_name,
                        service['config']['settings']['instance/os']
                        ['default']))
        if image == 'Ubuntu 11.10':
            image = 119
        if not name:
            name = 'CMDEP%s-server.stabletransit.com' % (deployment['id'][0:7])
        template = {'type': 'server', 'dns-name': name, 'flavor': flavor,
                'image': image, 'instance-id': None}

        return template
