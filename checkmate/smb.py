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

"""Remote calls over SMB (Windows) protocol."""

import logging
import os
import shlex
import signal
import socket
import subprocess
import tempfile
import time

import eventlet

LOG = logging.getLogger(__name__)


class Alarm(Exception):
    """Alarm Exception."""
    pass


def alarm_handler(signum, frame):  # pylint: disable=W0613
    """Called when a timeout signal is raised."""
    raise Alarm


# pylint: disable=R0913,R0914
def execute_script(host, script, remote_filename, username, password,
                   command=None, port=445, timeout=300):
    """Executes a powershell script on a remote windows host.

    :param host:            the ip address or host name of the remote server
    :param script:          the script to execute remotely
    :param remote_filename: the file name to use remotely
    :param username:        the username to use
    :param password:        password to use for username/password auth
    :param command:         optional command to use to run the script (defaults
                            to the script name which should be executable)
    :param port:            TCP IP port to use (smb default is 445)
    :param timeout:         timeout in seconds
    :returns: a dict with stdin and stdout of the call.
    """

    args = ''
    path = "temp"
    save_path = "c:\\windows\\%s" % path
    psexec = os.path.join(os.path.dirname(__file__), 'contrib', 'psexec.py')
    cmd = ("nice python %s -path '%s' '%s':'%s'@'%s' "
           "'c:\\windows\\sysnative\\cmd'" %
           (psexec, save_path, username, password, host))
    if command is None:
        command = ("c:\\windows\\system32\\windowspowershell\\v1.0\\"
                   "powershell.exe -ExecutionPolicy Bypass -Command \"%s\\%s\""
                   " %s;" % (save_path, remote_filename, args))

    if wait_net_service(host, port, timeout=timeout):
        temp_dir = tempfile.mkdtemp()
        script_path = None
        try:
            script_path = os.path.join(temp_dir, remote_filename)
            with open(script_path, 'w+b') as script_file:
                script_file.write(script)
            lines = "put %s %s\n%s\nexit\n" % (script_path, path, command)
            LOG.info("Executing powershell command '%s' on %s",
                     remote_filename, host)
            result = run_command(cmd, lines=lines, timeout=timeout)
            os.unlink(script_path)
            return result
        finally:
            if script_path and os.path.exists(script_path):
                os.unlink(script_path)
            os.removedirs(temp_dir)
    else:
        LOG.debug("Timeout executing powershell command '%s' on %s",
                  remote_filename, host)
        output = "Port 445 never opened up after %s seconds" % timeout
        status = 1

        return (status, output)
# pylint: enable=R0913,R0914


def wait_net_service(server, port, timeout=None):
    """Wait for network service to appear.

    :param timeout: in seconds, if None or 0 wait forever
    :return: True of False, if timeout is None may return only True or
             throw unhandled network exception
    """
    LOG.info("Waiting for %s/%s to respond", server, port)
    sock = socket.socket()
    if timeout:
        # time module is needed to calc timeout shared between two exceptions
        end = time.time() + timeout

    while True:
        try:
            if timeout:
                next_timeout = end - time.time()
                if next_timeout < 0:
                    LOG.info("Timeout waiting for %s/%s to respond", server,
                             port)
                    return False
                else:
                    sock.settimeout(next_timeout)

            sock.connect((server, port))

        except StandardError:
            # Handle refused connections, etc.
            if timeout:
                next_timeout = end - time.time()
                if next_timeout < 0:
                    LOG.info("Timeout waiting for %s/%s to respond", server,
                             port)
                    return False
                else:
                    sock.settimeout(next_timeout)

            eventlet.sleep(1)

        else:
            sock.close()
            LOG.info("%s/%s is responding", server, port)
            return True


def run_command(cmd, lines=None, timeout=None):
    """Executes commands against an executable.

    :param cmd: the command or shell to launch
    :param lines: a list of commands to execute
    :param timeout: in seconds
    :returns: status (0=success) + output as a string
    """
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
        LOG.info("Script run completed")
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
