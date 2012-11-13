#!/usr/bin/env python

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
__release__ = config.get("checkmate", "release")
__build_type__ = None


def get_build_type():
    global __build_type__
    if not __build_type__:
        import pkg_resources
        val = "unknown"
        try:
            dist = pkg_resources.get_distribution("checkmate")
            match = re.search('((\d+\.)+)(\D.+)', dist.version)
            if match:
                val = match.group(match.lastindex)
        except:
            pass
        __build_type__ = val
    return __build_type__


def version():
    return "%s-%s-%s" % (__version__, __release__, get_build_type())


print(version())
