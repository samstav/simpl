# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import unittest
import mox

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
    """Test Checkmate's built-in SSH Tasks"""

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_test_connection_key(self):
        """Test the test_connection function"""
        ip = "a.b.c.d"
        port = 44
        username = 'not-root'
        timeout = 15
        private_key = KEY
        identity_file = '~/.ssh/id_rsa'
        password = "secret"

        client = self.mox.CreateMockAnything()

        #Stub out _connect call
        self.mox.StubOutWithMock(ssh, 'connect')
        ssh.connect(ip, port=port, username=username, timeout=timeout,
                    private_key=private_key, identity_file=identity_file,
                    password=password).AndReturn(client)
        client.close().AndReturn(None)

        self.mox.ReplayAll()
        results = ssh.test_connection({}, ip, username, port=port,
                                      timeout=timeout, private_key=private_key,
                                      identity_file=identity_file,
                                      password=password)

        self.assertTrue(results, "Expecting a successful connection")
        self.mox.VerifyAll()

    def test_execute(self):
        """Test the ssh.execute function"""
        ip = "a.b.c.d"
        port = 44
        username = 'not-root'
        timeout = 15
        private_key = KEY
        identity_file = '~/.ssh/id_rsa'
        password = "secret"

        client = self.mox.CreateMockAnything()
        stdout = self.mox.CreateMockAnything()
        stdout.read().AndReturn("Outputs")
        stderr = self.mox.CreateMockAnything()
        stderr.read().AndReturn("Errors")

        #Stub out _connect call
        self.mox.StubOutWithMock(ssh, 'connect')
        ssh.connect(ip, port=port, username=username, timeout=timeout,
                    private_key=private_key, identity_file=identity_file,
                    password=password).AndReturn(client)
        client.exec_command('test').AndReturn((None, stdout, stderr))
        client.close().AndReturn(None)

        expected = {
            'stdout': "Outputs",
            'stderr': "Errors",
        }
        self.mox.ReplayAll()
        results = ssh.execute(ip, 'test', username, timeout=timeout,
                              password=password, identity_file=identity_file,
                              port=port, private_key=private_key)

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()

    def test_execute_2(self):
        """Test the ssh.execute_t function"""
        ip = "a.b.c.d"
        port = 44
        username = 'not-root'
        timeout = 15
        private_key = KEY
        identity_file = '~/.ssh/id_rsa'
        password = "secret"

        client = self.mox.CreateMockAnything()
        stdout = self.mox.CreateMockAnything()
        stdout.read().AndReturn("Outputs")
        stderr = self.mox.CreateMockAnything()
        stderr.read().AndReturn("Errors")

        #Stub out _connect call
        self.mox.StubOutWithMock(ssh, 'connect')
        ssh.connect(ip, port=port, username=username, timeout=timeout,
                    private_key=private_key, identity_file=identity_file,
                    password=password).AndReturn(client)
        client.exec_command('test').AndReturn((None, stdout, stderr))
        client.close().AndReturn(None)

        expected = {
            'stdout': "Outputs",
            'stderr': "Errors",
        }
        self.mox.ReplayAll()
        results = ssh.execute_2({}, ip, 'test', username, timeout=timeout,
                                password=password, identity_file=identity_file,
                                port=port, private_key=private_key)

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
