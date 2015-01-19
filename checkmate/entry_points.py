# Copyright (c) 2011-2013 Rackspace Hosting
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Things that should happen first (on app entry) go here."""

import os
import sys

# start tracer - pylint/flakes friendly
# NOTE: this will load checkmate which will monkeypatch if eventlet is
#       requested. We also load this ASAP so we can trace as much code as
#       possible. So position is important.  KEEP THIS FIRST
__import__('checkmate.common.tracer')


def preconfigure(args=None):
    """Common configuration to be done before everything else."""
    if os.getpid() == os.getpgid(os.getpid()):
        import checkmate
        strargv = " ".join(sys.argv)
        role = ''
        if 'checkmate-queue START' in strargv:
            role = 'Worker'
        elif 'server.py START' or 'checkmate-server START' in strargv:
            role = 'API'
        print("\n*** Staring Checkmate %s v%s Commit %s ***\n"
              % (role, checkmate.__version__, checkmate.__commit__[:8]))
    from checkmate.common import config

    args = args or sys.argv
    conf = config.current()
    conf.parse()
    if (conf.bottle_reloader and not conf.eventlet
            and not os.environ.get('BOTTLE_CHILD')):
        conf.quiet = True
        import logging
        logging.getLogger().setLevel(logging.ERROR)
    else:
        conf.init_logging(
            default_config='/etc/default/checkmate-svr-log.conf')

    if not conf.quiet:
        print(conf.display())


def client():
    """Entry point for Checkmate client."""

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

    for key in os.environ:
        if key.startswith('CHECKMATE_CLIENT'):
            print key, '=', os.environ[key]


def queue():
    """Entry point for Checkmate queue."""
    preconfigure()
    from checkmate import checkmate_queue
    checkmate_queue.main_func()


def server():
    """Entry point for Checkmate server."""
    preconfigure()
    from checkmate import server as cmserver
    cmserver.main()


def simulation():
    """Entry point for Checkmate simulation."""
    preconfigure()
    from checkmate.sample import checkmate_simulation
    checkmate_simulation.main_func()
