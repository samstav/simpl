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

# start tracer - pylint/flakes friendly
# NOTE: this will load checklmate which wil monkeypatch if eventlet is
#       requested. We also load this ASAP so we can trace as much code as
#       possible. So position is important.  KEEP THIS FIRST
__import__('checkmate.common.tracer')


def preconfigure():
    """Common configuration to be done before everything else."""
    from checkmate.common import config
    config.current().initialize()


def client():
    """Entry point for Checkmate client."""
    preconfigure()
    from checkmate import checkmate_client
    checkmate_client.main_func()


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
