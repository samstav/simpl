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
        """Generate a resource dict to be embedded in a  deployment"""
        pass

    def prep_environment(self, wfspec, deployment):
        """Add any tasks that are needed for an environment setup
        :returns: the final task that signifies readiness"""
        pass

    def add_resource_tasks(self, resource, key, wfspec, deployment,
            context, wait_on=None):
        """Add tasks needed to create a resource (the resource would normally
            what was generated in the generate_template call)
        :param wait_on: tasks to wait on before executing
        :returns: a hash (dict) of relevant tasks. The hash keys are:
                'root': the root task in the sequence
                'final': the task that signifies readiness (work is done)
        """
        pass


def get_provider_class(vendor, key):
    """Given a vendor name, and provider kjey, returjn the provider class"""
    name = "%s.%s" % (vendor, key)
    class_name = "checkmate.providers.%s" % name.replace('-', '_')
    LOG.debug("Instantiating provider class: %s" % class_name)
    return utils.import_class(class_name)
