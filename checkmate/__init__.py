import eventlet
eventlet.monkey_patch(socket=True, thread=True, os=True)

import gettext
import os
from ConfigParser import ConfigParser
import re

# This installs the _(...) function as a built-in so all other modules
# don't need to.
gettext.install('checkmate')

configfile = os.path.join(os.path.dirname(__file__), 'checkmate.cfg')
config = ConfigParser()
config.read(configfile)

__version__ = config.get("checkmate", "version")
__release__ = None


def load_release():
    global __release__
    import pkg_resources
    val = "unknown"
    try:
        dist = pkg_resources.get_distribution("checkmate")
        match = re.search('((\d+\.)+)(\D.+)', dist.version)
        if match:
            val = match.group(match.lastindex)
    except:
        pass
    __release__ = val

load_release()


def version():
    return "%s-%s" % (__version__, __release__)
