#!/usr/bin/env python

import gettext

# This installs the _(...) function as a built-in so all other modules
# don't need to.
gettext.install('checkmate')

__version__ = '0.2.2'
__release__ = 'alpha'

def version():
    return "%s %s - dev" % (__version__, __release__)
