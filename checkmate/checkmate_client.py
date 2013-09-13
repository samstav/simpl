#!/usr/bin/env python
import os

from checkmate.common import config
CONFIG = config.current()

print """
*** Checkmate Command-Line Client Utility ***

This tool is not ready yet. This file is being used to
reserve the name 'checkmate' as a command-line client
utility.

Too run the server, use one of these:
- checkmate-queue:  to manage the message queue listeners
- checkmate-server: to manage the REST server

Settings:
"""


def main_func():
    CONFIG.initialize()
    for key in os.environ:
        if key.startswith('CHECKMATE_CLIENT'):
            print key, '=', os.environ[key]

if __name__ == '__main__':
    main_func()
