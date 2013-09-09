'''Core Provider

Defined:
script   - a script configuration provider

'''
import logging

from celery import signals

from checkmate import providers

LOG = logging.getLogger(__name__)


def register():
    '''Register package providers.'''
    from checkmate.providers.core import script
    providers.register_providers([script.Provider])


@signals.celeryd_after_setup.connect
def register_tasks(**kwargs):
    """Register tasks in celery."""
    LOG.info("Initializing provider tasks %s", __name__)
    import checkmate.providers.core.script
