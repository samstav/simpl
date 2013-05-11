# pylint: disable=R0904,C0103
'''
Test SQLAlchemy using sqlite
'''
import sys

import base  # pylint: disable=W0403


class TestDBSQL(base.DBDriverTests):
    '''SQLAlchemy Driver Canned Tests'''

    connection_string = "sqlite://"


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
