#!/usr/bin/env python

import os
from pkg_resources import resource_filename


print """
*** Checkmate Server Simulator ***

Executes examples/app.yaml in simulation mode. This is for testing
and learning about CheckMate

Usage:

    checkmate-simulate


Settings:
"""

def main_func():
    for key in os.environ:
        if key.startswith('CHECKMATE_CLIENT'):
            print key, '=', os.environ[key]
    
    path = resource_filename(__name__, 'app.yaml')
    command = ("""CHECKMATE_CLIENT_TENANT=$(curl -H "X-Auth-User: """
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