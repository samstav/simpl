# Copyright (c) 2011-2015 Rackspace US, Inc.
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

"""Celery tasks to handle SSH connections."""

import logging
import os
import StringIO

from celery.task import task
import paramiko
from satori import bash
from satori import ssh

from checkmate.common import statsd
from checkmate import smb
from checkmate.utils import match_celery_logging

LOG = logging.getLogger(__name__)


class AcceptMissingHostKey(paramiko.client.MissingHostKeyPolicy):

    """Add missing host keys to the client.

    Do not save in the known_hosts file since we can easily spin up servers
    that have recycled ip addresses
    """

    def missing_host_key(self, client, hostname, key):
        client._host_keys.add(hostname, key.get_name(), key)


def get_gateway(address, username=None, password=None, private_key=None,
                key_filename=None):
    """Return a satori SSH client to use as an ssh gateway."""
    options = {'StrictHostKeyChecking': False}
    return ssh.connect(address, username=username,
                       password=password,
                       private_key=private_key,
                       key_filename=key_filename,
                       options=options)


@task(default_retry_delay=10, max_retries=36)
@statsd.collect
def test_connection(context, ip, username, timeout=10, password=None,
                    identity_file=None, port=22,
                    private_key=None, proxy_address=None,
                    proxy_credentials=None):
    """Connect to an ssh server and verify that it responds.

    ip:             the ip address or host name of the server
    username:       the username to use
    timeout:        timeout in seconds
    password:       password to use for username/password auth
    identity_file:  a private key file to use
    port:           TCP IP port to use (ssh default is 22)
    private_key:    an RSA string for the private key to use (instead of using
                    a file)

    The order for authentication attempts is:
    - private_key
    - identity_file
    - any key discoverable in ~/.ssh/
    - username/password
    """
    match_celery_logging(LOG)
    LOG.debug("Checking for a response from ssh://%s@%s:%d.", username, ip,
              port)
    if proxy_address:
        gateway = get_gateway(proxy_address, **proxy_credentials)
    else:
        gateway = None
    try:
        client = connect(ip, port=port, username=username, timeout=timeout,
                         private_key=private_key, identity_file=identity_file,
                         password=password, gateway=gateway)
        client.close()
        LOG.debug("ssh://%s@%s:%d is up.", username, ip, port)
        return True
    except Exception as exc:
        LOG.info('ssh://%s@%s:%d failed.  %s', username, ip, port, exc)
        if test_connection.request.id:
            test_connection.retry(exc=exc)
    return False


@task(default_retry_delay=10, max_retries=10)
@statsd.collect
def execute_2(context, ip_address, command, username, timeout=10,
              password=None, identity_file=None, port=22, private_key=None,
              proxy_address=None, proxy_credentials=None):
    """Execute function that takes a context and handles simulations."""
    if context.get('simulation') is True:
        results = {
            'stdout': "DUMMY OUTPUT",
            'stderr': "DUMMY STDERR",
        }
        return results
    return execute(ip_address, command, username, timeout=timeout,
                   password=password, identity_file=identity_file, port=port,
                   private_key=private_key, proxy_address=proxy_address,
                   proxy_credentials=proxy_credentials)


@task(default_retry_delay=10, max_retries=10)
@statsd.collect
def execute(ip, command, username, timeout=10, password=None,
            identity_file=None, port=22, private_key=None,
            proxy_address=None, proxy_credentials=None):
    """Execute an ssh command on a remote host.

    Tries cert auth first and falls back to password auth if password provided

    ip:                 the ip address or host name of the server
    command:            shell command to execute
    username:           the username to use
    timeout:            timeout in seconds
    password:           password to use for username/password auth
    identity_file:      a private key file to use
    port:               TCP IP port to use (ssh default is 22)
    private_key:        an RSA string for the private key to use (instead of
                        using a file)
    proxy_address:      optional proxy server address
    proxy_credentials:  dict of username and password or private_key for proxy
    :returns: a dict with stdin and stdout of the call.
    """
    match_celery_logging(LOG)
    LOG.debug("Executing '%s' on ssh://%s@%s:%s.", command, username, ip, port)
    if proxy_address:
        gateway = get_gateway(proxy_address, **proxy_credentials)
    else:
        gateway = None
    try:
        results = remote_execute(ip, command, username, password=password,
                                 identity_file=identity_file,
                                 private_key=private_key, port=port,
                                 timeout=timeout, gateway=gateway)
        return results
    except Exception as exc:
        LOG.info("ssh://%s@%s:%d failed.  %s", username, ip, port, exc)
        execute.retry(exc=exc)


def remote_execute(host, command, username, password=None, identity_file=None,
                   private_key=None, port=22, timeout=10, gateway=None):
    """Execute an ssh command on a remote host.

    Tries cert auth first and falls back to password auth if password provided

    :param host:           the ip address or host name of the server
    :param command:        shell command to execute
    :param username:       the username to use
    :param password:       password to use for username/password auth
    :param identity_file:  a private key file to use
    :param private_key:    an RSA string for the private key to use (instead of
                           using a file)
    :param port:           TCP IP port to use (ssh default is 22)
    :param timeout:        timeout in seconds
    :returns: a dict with stdin and stdout of the call.
    """
    LOG.debug("Executing '%s' on ssh://%s@%s:%s.", command, username, host,
              port)
    client = None
    try:
        client = connect(host, port=port, username=username, timeout=timeout,
                         private_key=private_key, identity_file=identity_file,
                         password=password, gateway=gateway)
        results = client.execute(command)
        LOG.debug('ssh://%s@%s:%d responded.', username, host, port)
        return results
    except Exception as exc:
        LOG.info("ssh://%s@%s:%d failed.  %s", username, host, port, exc)
        raise
    finally:
        if client:
            client.close()


def connect(ip, port=22, username="root", timeout=10, identity_file=None,
            private_key=None, password=None, gateway=None):
    """Attempt SSH connection and returns SSHClient object.

    ip:             the ip address or host name of the server
    username:       the username to use
    timeout:        timeout in seconds
    password:       password to use for username/password auth
    identity_file:  a private key file to use
    port:           TCP IP port to use (ssh default is 22)
    private_key:    an RSA string for the private key to use (instead of using
                    a file)
    """
    try:
        options = {'StrictHostKeyChecking': False}
        if private_key is not None:
            file_obj = StringIO.StringIO(private_key)
            pkey = paramiko.RSAKey.from_private_key(file_obj)
            LOG.debug("Trying supplied private key string")
            client = bash.RemoteShell(ip, timeout=timeout, port=port,
                                      username=username, private_key=pkey,
                                      gateway=gateway, options=options)
        elif identity_file is not None:
            LOG.debug("Trying key file: %s", os.path.expanduser(identity_file))
            client = bash.RemoteShell(
                ip, timeout=timeout, port=port, username=username,
                key_filename=os.path.expanduser(identity_file),
                gateway=gateway, options=options)
        else:
            client = bash.RemoteShell(ip, port=port, username=username,
                                      password=password, gateway=gateway,
                                      options=options)
            LOG.debug("Authentication for ssh://%s@%s:%d using "
                      "password succeeded", username, ip, port)
        LOG.debug("Connected to ssh://%s@%s:%d.", username, ip, port)
        return client
    except paramiko.PasswordRequiredException:
        # Looks like we have cert issues, so try password auth if we can
        if password:
            LOG.debug("Retrying with password credentials")
            return connect(ip, username=username, timeout=timeout,
                           password=password, port=port)
        else:
            raise
    except paramiko.BadHostKeyException as exc:
        msg = ("ssh://%s@%s:%d failed:  %s. You might have a bad key "
               "entry on your server, but this is a security issue and won't "
               "be handled automatically. To fix this you can remove the "
               "host entry for this host from the /.ssh/known_hosts file" %
               (username, ip, port, exc))
        LOG.info(msg)
        raise
    except Exception as exc:
        LOG.info('ssh://%s@%s:%d failed.  %s', username, ip, port, exc)
        raise


def ps_execute(host, script, filename, username, password, port=445,
               timeout=300, gateway=None):
    """Make ps_exec available to be used as an api object in compute."""
    return smb.execute_script(host, script, filename, username, password,
                              port=port, timeout=timeout, gateway=gateway)
