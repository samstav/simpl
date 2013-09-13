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
from checkmate import checkmate_client
from checkmate import checkmate_database
from checkmate import checkmate_queue
from checkmate.common import config
from checkmate.sample import checkmate_simulation
from checkmate import server as cmserver


def preconfigure():
    """Common configuration to be done before everything else."""
    config.current().initialize()


def client():
    """Entry point for Checkmate client."""
    preconfigure()
    checkmate_client.main_func()


def database():
    """Entry point for Checkmate database."""
    preconfigure()
    checkmate_database.main_func()


def queue():
    """Entry point for Checkmate queue."""
    preconfigure()
    checkmate_queue.main_func()


def server():
    """Entry point for Checkmate server."""
    preconfigure()
    cmserver.main()


def simulation():
    """Entry point for Checkmate simulation."""
    preconfigure()
    checkmate_simulation.main_func()
