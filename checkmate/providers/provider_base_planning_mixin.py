import os
import logging

LOG = logging.getLogger(__name__)


class ProviderBasePlanningMixIn(object):
    """The methods used by the deployment planning code (i.e. they need a
    deployment to work on)

    This class is mixed in to the ProviderBase
    """

    def get_resource_name(self, deployment, domain, index, service,
                          resource_type):
        if service:
            if deployment._constrained_to_one(service):
                name = "%s.%s" % (service, domain)
            elif isinstance(index, int) or (isinstance(index, basestring) and
                                            index.isdigit()):
                name = "%s%02d.%s" % (service, int(index), domain)
            else:
                name = "%s%s.%s" % (service, index, domain)
        else:
            name = "shared%s.%s" % (resource_type, domain)
        return name

    def generate_template(self, deployment, resource_type, service, context,
                          index, provider_key, definition):
        LOG.debug("Getting %s template for service %s", resource_type, service)
        default_domain = os.environ.get('CHECKMATE_DOMAIN',
                                        'checkmate.local')
        domain = deployment.get_setting('domain',
                                        provider_key=provider_key,
                                        resource_type=resource_type,
                                        service_name=service,
                                        default=default_domain)
        result = dict(type=resource_type, provider=provider_key, instance={})
        if service:
            result['service'] = service

        name = self.get_resource_name(deployment, domain, index, service,
                                      resource_type)
        result['dns-name'] = name
        return [result]

    @staticmethod
    def generate_resource_tag(base_url=None, tenant_id=None,
                              deployment_id=None, resource_id=None):
        '''Builds the URL to a Resource used in RAX-CHECKMATE metadata'''
        return {
            'RAX-CHECKMATE': "{}/{}/deployments/{}/resources/{}"
            .format(base_url, tenant_id, deployment_id, resource_id)
        }

    def verify_limits(self, context, resources):
        """Implemented in the specific Provider classes"""
        pass

    def verify_access(self, context):
        """Implemented in the specific Provider classes"""
        pass
