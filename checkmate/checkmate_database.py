#!/usr/bin/env python
import os
import sys

from migrate.versioning.shell import main


def main_func():
    url = os.environ['CHECKMATE_CONNECTION_STRING']
    
    import checkmate.db.repository
    repo = os.path.dirname(checkmate.db.repository.__file__)

    print "*** CheckMate Database Versioning Tool ***\n"
    print "DATABASE: %s" % url
    print "REPOSITORY: %s\n" % repo

    try:
        main(url=os.environ['CHECKMATE_CONNECTION_STRING'], debug='False',
                repository=repo)
    except Exception as exc:
        sys.exit("%s: %s" % (exc.__class__.__name__, exc))
    print "\nOperation Completed Successfully"

if __name__ == '__main__':
    main_func()
