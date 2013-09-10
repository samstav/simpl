#!/usr/bin/env python

# Copyright (c) 2011-2013 Rackspace Hosting
# All Rights Reserved.
#
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

import os
import pkg_resources
import sys

print """
*** Checkmate Server Simulator ***

Executes examples/app.yaml in simulation mode. This is for testing
and learning about Checkmate

Usage:

    checkmate-simulate


Settings:
"""

if 'CHECKMATE_CLIENT_USERNAME' not in os.environ:
    sys.exit("CHECKMATE_CLIENT_USERNAME not set in environment")

if 'CHECKMATE_CLIENT_APIKEY' not in os.environ:
    sys.exit("CHECKMATE_CLIENT_APIKEY not set in environment")


def main_func():
    """Run a simulation."""
    for key in os.environ:
        if key.startswith('CHECKMATE_CLIENT'):
            print key, '=', os.environ[key]

    path = pkg_resources.resource_filename(__name__, 'app.yaml')
    command = (
        """CHECKMATE_CLIENT_TENANT=$(curl -H "X-Auth-User: """
        """${CHECKMATE_CLIENT_USERNAME}" -H "X-Auth-Key: """
        """${CHECKMATE_CLIENT_APIKEY}" """
        """-I https://identity.api.rackspacecloud.com/v1.0 -v 2> /dev/null """
        """| grep "X-Server-Management-Url" | grep -P -o $'(?!.*/).+$'| """
        """tr -d '\r') && CHECKMATE_CLIENT_TOKEN=$(curl -H "X-Auth-User: """
        """${CHECKMATE_CLIENT_USERNAME}" -H "X-Auth-Key: """
        """${CHECKMATE_CLIENT_APIKEY}" """
        """-I https://identity.api.rackspacecloud.com/v1.0 -v 2> /dev/null """
        """| grep "X-Auth-Token:" | awk '/^X-Auth-Token:/ { print $2 }') """
        """&& awk '{while(match($0,"[$][\\{][^\\}]*\\}")) """
        """{var=substr($0,RSTART+2,RLENGTH -3);gsub("[$][{]"var"[}]","""
        """ENVIRON[var])}}1' < %s | curl -H "X-Auth-Token: """
        """${CHECKMATE_CLIENT_TOKEN}" -H 'content-type: application/x-yaml'"""
        """ http://localhost:8080/${CHECKMATE_CLIENT_TENANT}/deployments/"""
        """simulate -v --data-binary @-""" % path)

    print 'Executing this command:\n\n%s\n' % command
    os.system(command)


if __name__ == '__main__':
    main_func()
