# pylint: disable=C0103,W0603
'''
Checkmate Server

Note: To support running with a wsgiref server with auto reloading and also
full eventlet support, we need to handle eventlet up front. If we are using
eventlet, then we'll monkey_patch ASAP. If not, then we won't monkey_patch at
all as that breaks reloading.
'''
# BEGIN: ignore style guide
# monkey_patch ASAP if we're using eventlet
import sys
if '--eventlet' in sys.argv:
    try:
        import eventlet
        eventlet.monkey_patch(socket=True, thread=True, os=True)
    except ImportError:
        pass  # OK if running setup.py or not using eventlet somehow
# END: ignore style guide

import ConfigParser
import gettext
import os
import re

# This installs the _(...) function as a built-in so all other modules
# don't need to.
gettext.install('checkmate')


def _get_version():
    '''Return version information from checkmate.cfg.'''
    configfile = os.path.join(os.path.dirname(__file__), 'checkmate.cfg')
    config = ConfigParser.ConfigParser()
    config.read(configfile)
    return config.get("checkmate", "version")


def _get_release():
    '''Load release information from checkmate.cfg.'''
    val = "unknown"
    try:
        import pkg_resources
        dist = pkg_resources.get_distribution("checkmate")
        # pylint: disable=E1103
        match = re.search(r'((\d+\.)+)(\D.+)', dist.version)
        if match:
            val = match.group(match.lastindex)
    except StandardError:
        pass
    return val


__version__ = _get_version()
__release__ = _get_release()


def version():
    '''Return checkmate server version as a string.'''
    return "%s-%s" % (__version__, __release__)
