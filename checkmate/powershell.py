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

# authorship credit to Trey Tabner/ServerMill

"""PowerShell calls."""

import logging
import os
import shlex
import signal
import socket
import subprocess
import time

import eventlet

LOG = logging.getLogger(__name__)


class Alarm(Exception):
    """Alarm Exception."""
    pass


# pylint: disable=W0613
def alarm_handler(signum, frame):
    """Called when a timeout signal is raised."""
    raise Alarm


def execute(host, command, filename, username, password, port=445,
            timeout=300):
    """Executes an powershell command on a remote windows host.

    :param host:           the ip address or host name of the server
    :param command:        shell command to execute
    :param filename:       the name of the file being run
    :param username:       the username to use
    :param password:       password to use for username/password auth
    :param port:           TCP IP port to use (smb default is 445)
    :param timeout:        timeout in seconds
    :returns: a dict with stdin and stdout of the call.
    """
    path = "temp"
    save_path = "c:\\windows\\%s" % path
    psexec = os.path.join(os.path.dirname(__file__), 'contrib', 'psexec.py')
    cmd_string = "nice python %s -path '%s' '%s':'%s'@'%s' " \
                 "'c:\\windows\\sysnative\\cmd'"
    cmd = cmd_string % (psexec, save_path, username, password, host)
    lines = "put %s %s\n%s\nexit\n" % (filename, path, command)

    LOG.info("Executing powershell command '%s' on %s", filename, host)
    if wait_net_service(host, port, timeout=timeout):
        return run_command(cmd, lines=lines, timeout=timeout)
    else:
        LOG.debug("Timeout executing powershell command '%s' on %s", filename,
                  host)
        output = "Port 445 never opened up after %s seconds" % timeout
        status = 1

        return (status, output)


def wait_net_service(server, port, timeout=None):
    """Wait for network service to appear.

    :param timeout: in seconds, if None or 0 wait forever
    :return: True of False, if timeout is None may return only True or
             throw unhandled network exception
    """
    sock = socket.socket()
    if timeout:
        # time module is needed to calc timeout shared between two exceptions
        end = time.time() + timeout

    while True:
        try:
            if timeout:
                next_timeout = end - time.time()
                if next_timeout < 0:
                    return False
                else:
                    sock.settimeout(next_timeout)

            sock.connect((server, port))

        except Exception:
            # Handle refused connections, etc.
            if timeout:
                next_timeout = end - time.time()
                if next_timeout < 0:
                    return False
                else:
                    sock.settimeout(next_timeout)

            eventlet.sleep(1)

        else:
            sock.close()
            return True


def run_command(cmd, lines=None, timeout=None):
    """TODO: docs."""
    LOG.debug("Executing: %s", cmd)
    proc = subprocess.Popen(shlex.split(cmd),
                            close_fds=True,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)

    signal.signal(signal.SIGALRM, alarm_handler)
    if timeout:
        signal.alarm(timeout)

    try:
        if lines:
            (stdout, stderr) = proc.communicate(input=lines)
            LOG.debug("Response: stdout=%s, stderr=%s", stdout, stderr)

        status = proc.wait()
        signal.alarm(0)
    except Alarm:
        LOG.info("Timeout running script")
        status = 1
        stdout = ''
        proc.kill()

    if lines:
        output = stdout

        # Remove this cruft from Windows output
        output = output.replace('\x08', '')
        output = output.replace('\r', '')

    else:
        output = proc.stdout.read().strip()

    return (status, output)
