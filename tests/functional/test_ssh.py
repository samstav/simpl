# pylint: disable=E1103

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

"""Tests for SSH."""
import mock
import unittest

from checkmate import ssh

KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEpQIBAAKCAQEAyIPPUc5/JEBLZMvvcfJjNtFODwO4FsbGsCDn0KW4ftt1Vo/T
Qo6N066k1s03/H+B+N6DZYKU5EP2pFkPM2QTSU7WMOdtdHKlOUdzLOKwtztNs4Yf
/c+d6ySo6YHe0PBhwf20f5FiI1qbA+DTDGOkqo8/KL02MHn6w+0/aBxiX93qcNup
KkA91nP3ib1DgH3ODwu0NYgjayYQ/xTkX9WVlBDMkmD9Fc9wAEzBUID07CViTRMH
LUOzbGDPFUYMT+EBcM+deDOcTwu2nNCBn5cIpIkcPrcHmmSJbdBiZGmsEfmaI8zi
HEBGP1FRuuzvenNF2J3uJA6RBGBYfpEVNUcqzQIDAQABAoIBAQCLFCnr0zAK4/Gn
c3Cc94PrlNfwwCKi4bMUnW5NIXVLwEquBMqC4r/q8LrzJprLr2FmTmiTMzS085MS
wZcyjRp3gZA9kXgxCggiJ7XyjzYFkcO+Xqy37pbZb68db/Atul4EIUZeKWgJn6Hf
2cRpVn/zsbIcPslkbGcMGPYe73kohlg1xjq+o/uqG8IL7oA/RqWpcT9ccyHl2LhI
wl8n28YaEcii+3sM/1gHx+UubVCOQjN7384TYQD/HtOJHcADQDeRsVkHmlGR4JTw
W7FXC1J572lKR282TFDgrWmdPBYCQ+0N1BqKrJZo3CqgCjeSGKtapjSRJ/dF+QI+
04tsP+/BAoGBANNoncCbKG+JcgY5Bo839O/kvThsBXRw0cQ3L80qMvlzWSCC9plj
8a2tBy1o3R3oheVNIXF9raxJFajy5h0+r1TYOrIEJ7FZwbtNBIF6HLpsJ6Q4YP1q
rafrHO7gm29RfPxn3M937kjnNVTjdpLfniRcRKXpio6zWYIkDOUF/SsRAoGBAPLO
9wq4t+haPs2yUbRS8r/sLC6W7e/sNQgyAl1cvIhlLVBzY4ejo2uRfE0YgODgrgCr
HKDHf25wehjCYvIyySr3VeFOJh8BVCXe6tAzGkyRlmILxbDnKfU+ehuPn2LH4D0y
bYLZWmzpQ1bXMtQhUlw72fcVxvB4UrZA+8JM2+v9AoGAA/H0165Nj99JwHH5/Fw3
9u4W1eG2LFkaoQXCn5qE/wC3DhNDlNM3pF0RQDivv6oiLYhF8n886XUnsVJvFuaf
kP7EAaRwNTAOnHcweVYVCSmRh9ABh1khSnvpu093txkXMwKhLUH4sWWXKjFgehcw
NU9/fHUiP817AyG3F+MHuXECgYEA6e9pqRTLa7v3ImuZuKjqZOsArmqQGEZ12c2E
5brBkpAYlph13mtUugDTx9vB3+fY/Z/e1zEen6MSn+Q5PKydkR33yjlnFRxMnKgn
iCyUPA1Q3GoHMCeoDzcAoqk/oQZ+D7gUNqt/KcucK4Du4d6w4Vhw6lQ69diXqCz3
4v32LWkCgYEArXSwg+J6paa8LCFr1glGC+kAXzgGlrLWjShAF+UxqlsbkLl13jbw
gVLiU0oxARB/VRH8lhrZZVLAbzfe9axK79L1JEcYa/8HGG0nT4z3NiuRY5xoExkM
HNLoMGWDbYkodusmrHUN5Ed3E3w8Y+wpREa7vhX4Mey98gQ7Sgwcu0U=
-----END RSA PRIVATE KEY-----"""


class TestSSH(unittest.TestCase):
    """Test Checkmate's built-in SSH Tasks."""

    @mock.patch.object(ssh, 'connect')
    def test_test_connection_key(self, mock_connect):
        """Test the test_connection function."""
        ip_addr = "a.b.c.d"
        port = 44
        username = 'not-root'
        timeout = 15
        private_key = KEY
        identity_file = '~/.ssh/id_rsa'
        password = "secret"

        client = mock.Mock()

        #Stub out _connect call
        mock_connect.return_value = client
        client.close.return_value = None

        results = ssh.test_connection({}, ip_addr, username, port=port,
                                      timeout=timeout, private_key=private_key,
                                      identity_file=identity_file,
                                      password=password)

        self.assertTrue(results, "Expecting a successful connection")
        mock_connect.assert_called_with(ip_addr, port=port, username=username,
                                        timeout=timeout,
                                        private_key=private_key,
                                        identity_file=identity_file,
                                        password=password)

    @mock.patch.object(ssh, 'connect')
    def test_execute(self, mock_connect):
        """Test the ssh.execute function."""
        ip_addr = "a.b.c.d"
        port = 44
        username = 'not-root'
        timeout = 15
        private_key = KEY
        identity_file = '~/.ssh/id_rsa'
        password = "secret"

        client = mock.Mock()
        stdout = mock.Mock()
        stdout.read.return_value = "Outputs"
        stderr = mock.Mock()
        stderr.read.return_value = "Errors"

        #Stub out _connect call
        mock_connect.return_value = client
        client.exec_command.return_value = (None, stdout, stderr)
        client.close.return_value = None

        expected = {
            'stdout': "Outputs",
            'stderr': "Errors",
        }
        results = ssh.execute(ip_addr, 'test', username, timeout=timeout,
                              password=password, identity_file=identity_file,
                              port=port, private_key=private_key)

        self.assertDictEqual(results, expected)
        client.exec_command.assert_called_with('test')
        mock_connect.assert_called_with(ip_addr, port=port,
                                        username=username,
                                        timeout=timeout,
                                        private_key=private_key,
                                        identity_file=identity_file,
                                        password=password)

    @mock.patch.object(ssh, 'connect')
    def test_execute_2(self, mock_connect):
        """Test the ssh.execute_t function."""
        ip_addr = "a.b.c.d"
        port = 44
        username = 'not-root'
        timeout = 15
        private_key = KEY
        identity_file = '~/.ssh/id_rsa'
        password = "secret"

        client = mock.Mock()
        stdout = mock.Mock()
        stdout.read.return_value = "Outputs"
        stderr = mock.Mock()
        stderr.read.return_value = "Errors"

        mock_connect.return_value = client
        client.exec_command.return_value = (None, stdout, stderr)
        client.close.return_value = None

        expected = {
            'stdout': "Outputs",
            'stderr': "Errors",
        }
        results = ssh.execute_2({}, ip_addr, 'test', username, timeout=timeout,
                                password=password, identity_file=identity_file,
                                port=port, private_key=private_key)

        self.assertDictEqual(results, expected)
        client.exec_command.assert_called_with('test')
        mock_connect.assert_called_with(ip_addr,
                                        port=port,
                                        username=username,
                                        timeout=timeout,
                                        private_key=private_key,
                                        identity_file=identity_file,
                                        password=password)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
