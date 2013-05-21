#!/usr/bin/env python
import os
import sys

from migrate.versioning.shell import main


def main_func():
    url = os.environ['CHECKMATE_CONNECTION_STRING']

    import checkmate.db.repository
    repo = os.path.dirname(checkmate.db.repository.__file__)

    print "*** Checkmate Database Versioning Tool ***\n"
    print "DATABASE: %s" % url
    print "REPOSITORY: %s\n" % repo
    print "\n"
    print "NOTE: A significant change was made in v0.12 to the Deployment\n"
    print "      class in sql.py. A new attribute – status – was added, the\n"
    print "      value of which is populate from the 'status' key in\n"
    print "      Deployment.body. This means that deployments saved prior to\n"
    print "      v0.12 will not have this column populated. No migration has\n"
    print "      been created at this point, but the data should be saved\n"
    print "      with the next save_deployment.\n"
    print "\n"
    print "YOU HAVE BEEN WARNED.\n"

    try:
        main(url=os.environ['CHECKMATE_CONNECTION_STRING'], debug='False',
                repository=repo)
    except Exception as exc:
        sys.exit("%s: %s" % (exc.__class__.__name__, exc))
    print "\nOperation Completed Successfully"

if __name__ == '__main__':
    main_func()
