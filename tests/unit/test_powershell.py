# pylint: disable=R0904,W0613,C0111

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

"""Tests for Admin endpoints."""

import unittest

import mock

from checkmate import powershell


class TestPowershell(unittest.TestCase):

    @mock.patch.object(powershell, 'wait_net_service')
    @mock.patch.object(powershell, 'run_command')
    @mock.patch.object(powershell, 'os')
    def test_execute(self, os_mock, run_mock, wait_mock):
        os_mock.path.dirname.return_value = 'X'
        os_mock.path.join.return_value = '/path/psexec.py'
        wait_mock.return_value = True
        run_mock.return_value = (0, 'X')
        result = powershell.execute('localhost', 'foo 2', 'install.ps1',
                                    'Admin', 'secret')
        self.assertEqual(result, (0, 'X'))
        command = ("nice python /path/psexec.py -path 'c:\\windows\\temp' 'Adm"
                   "in':'secret'@'localhost' 'c:\\windows\\sysnative\\cmd'")
        lines = "put install.ps1 temp\nfoo 2\nexit\n"
        run_mock.assert_called_with(command, lines=lines, timeout=300)
        wait_mock.assert_called_with('localhost', 445, timeout=300)

    @mock.patch.object(powershell, 'wait_net_service')
    @mock.patch.object(powershell, 'os')
    def test_execute_fail(self, os_mock, wait_mock):
        os_mock.path.dirname.return_value = 'X'
        os_mock.path.join.return_value = '/path/psexec.py'
        wait_mock.return_value = False
        result = powershell.execute('localhost', 'foo 2', 'install.ps1',
                                    'Admin', 'secret')
        msg = "Port 445 never opened up after 300 seconds"
        self.assertEqual(result, (1, msg))
        wait_mock.assert_called_with('localhost', 445, timeout=300)

    @mock.patch.object(powershell, 'socket')
    def test_wait_net_service(self, mock_socket):
        mock_sock = mock.Mock()
        mock_socket.socket.return_value = mock_sock
        mock_sock.settimeout.return_value = None
        mock_sock.connect.return_value = None
        mock_sock.close.return_value = None
        result = powershell.wait_net_service('localhost', 500, timeout=2)
        self.assertTrue(result)

    @mock.patch.object(powershell, 'socket')
    def test_wait_net_service_fail_once(self, mock_socket):
        mock_sock = mock.Mock()
        mock_socket.socket.return_value = mock_sock
        mock_sock.settimeout.return_value = None

        returns = [Exception('boom'), 'response']

        def side_effect(*args):
            result = returns.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        mock_connect = mock.Mock(side_effect=side_effect, return_value=None)
        mock_sock.connect = mock_connect
        mock_sock.close.return_value = None
        result = powershell.wait_net_service('localhost', 500, timeout=2)
        calls = [mock.call(('localhost', 500)), mock.call(('localhost', 500))]
        self.assertEqual(mock_connect.call_args_list, calls)
        self.assertTrue(result)

    @mock.patch.object(powershell, 'subprocess')
    def test_run_command(self, subprocess_mock):
        proc_mock = mock.Mock()
        subprocess_mock.Popen.return_value = proc_mock
        subprocess_mock.PIPE = None
        subprocess_mock.STDOUT = None
        proc_mock.wait = mock.Mock(return_value=0)
        proc_mock.stdout.read = mock.Mock(return_value='X')

        result = powershell.run_command('test 2')
        self.assertEqual(result, (0, 'X'))
        subprocess_mock.Popen.assert_called_with(['test', '2'], close_fds=True,
                                                 stdin=None,
                                                 stdout=None,
                                                 stderr=None)


if __name__ == '__main__':
    import sys
    from checkmate import test as cmtest
    cmtest.run_with_params(sys.argv[:])
