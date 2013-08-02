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
try:
    import eventlet
    if '--eventlet' in sys.argv:
        eventlet.monkey_patch(socket=True, thread=True, os=True)
    else:
        # Only patch socket so that httplib, urllib type libs are green
        eventlet.monkey_patch(socket=True)
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


configfile = os.path.join(os.path.dirname(__file__), 'checkmate.cfg')
config = ConfigParser.ConfigParser()
config.read(configfile)

__version__ = config.get("checkmate", "version")


def version():
    '''Return checkmate server version as a string.'''
    return __version__
