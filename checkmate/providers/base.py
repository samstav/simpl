import logging

from checkmate import utils

LOG = logging.getLogger(__name__)


class ProviderBase():
    def __init__(self, provider):
        self.dict = provider

    def provides(self):
        """Returns  a list of resources that this provider can provder"""
        return self.dict.get('provides', [])

    def generate_template(self, deployment, service_name, service, name=None):
        """Generate a resource dict to be embedded ina  deployment"""
        raise NotImplementedError()

    def prep_environment(self, wfspec, deployment):
        """Asdd any tasks that are needed for an environment setup"""
        raise NotImplementedError()

    def add_resource_tasks(self, resource, key, wfspec, deployment,
            context, wait_on=None):
        """Add tasks needed to create a resource (the resource would normally
            what was generated in the generate_template call)"""
        raise NotImplementedError()


def get_provider_class(vendor, key):
    """Given a vendor name, and provider kjey, returjn the provider class"""
    name = "%s.%s" % (vendor, key)
    class_name = "checkmate.providers.%s" % name.replace('-', '_')
    LOG.debug("Instantiating provider class: %s" % class_name)
    return utils.import_class(class_name)
