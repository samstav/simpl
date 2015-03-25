#!/usr/bin/env python

"""Bootstrap Python keyring for a development environment.

This script will seed the Python keyring with the settings needed to
run Checkmate locally. It will ask for your Rackspace SSO credentials, use
these to extract the secrets from PasswordSafe, and finally store
these in the keyring.
"""

import getpass
import json
import pprint
import sys

import keyring
import requests
from simpl import config

PROJECT_NAME = 'checkmate'


class PasswordSafeWrapper(object):
    def __init__(self,
                 passwordsafe_url,
                 project_name,
                 auth_token,
                 env_vars):

        # We are not retrying on failed auth token as it is once and done.
        self.auth_token = auth_token
        self.env_vars = env_vars
        self.passwordsafe_url = passwordsafe_url
        self.project_name = project_name

        # Establishing reusable session
        self.sess = self._get_session()

        # Retrieving needed info from PS
        self.project_id = self.get_project_id()
        self._ps_credentials = self._get_project_credentials()

        # Building a list of secrets
        self.secrets = self.build_secrets()

    def _get_session(self):
        sess = requests.Session()
        sess.headers = {'content-type': 'application/json',
                        'accept': 'application/json',
                        'x-auth-token': self.auth_token}
        return sess

    def username(self, config_entry_name, ps_id=None):
        """ Convenience method for grabbing a username from passwordsafe."""
        return self.get_matching_credentials('username', config_entry_name,
                                             ps_id)

    def password(self, config_entry_name, ps_id=None):
        """ Convenience method for grabbing a password from passwordsafe."""
        return self.get_matching_credentials('password', config_entry_name,
                                             ps_id)

    def hostname(self, config_entry_name, ps_id=None):
        """ Convenience method for grabbing a hostname from passwordsafe."""
        return self.get_matching_credentials('hostname', config_entry_name,
                                             ps_id)

    def get_matching_credentials(self, ps_field, config_entry_name,
                                 ps_id=None):
        """
        Retrieves a field from passwordsafe based on the prerequisites field.
        A passwordsafe id can be specified to force an explicit match.

        Example: get_matching_credentials('password', 'github_teams')
        This will return the password for the checkmate passwordsafe project that
        has github_teams specified in the prerequisites field.

        :param ps_field: The field from passwordsafe that is to be returned
        :param config_entry_name: The name of config entry.
        :param ps_id: A passwordsafe id.
        :return: The value stored in passwordsafe for the given ps_field
        :raises LookupError: When the number of creds found is not exactly 1.
        """
        results = []
        for cred in self._ps_credentials:
            # Since the password safe ID is guaranteed to be unique we return
            if ps_id == cred['id']:
                return cred[ps_field]
            elif config_entry_name == cred['prerequisites']:
                results.append(cred)

        if not results:
            raise LookupError('No credentials found for %s' %
                              config_entry_name)
        elif len(results) > 1:
            raise LookupError('Too many results found. Conflicting IDs: %s'
                              % [item['id'] for item in results])
        else:
            return results[0][ps_field]

    def _get_project_credentials(self, retry=True):
        output('retrieving credentials')
        resp = self.sess.get(self.passwordsafe_url +
                             '/projects/%s/credentials' %
                             self.project_id)

        # PS has a tendency to occasionally return 403's
        # adding in a single retry to alleviate this.
        if retry and resp.status_code == 403:
            self._get_project_credentials(retry=False)
        resp.raise_for_status()
        credentials = [result['credential'] for result in resp.json()]
        output('found %d credentials', len(credentials))
        return credentials

    def get_project_id(self):
        output('retrieving project ID')
        resp = self.sess.get(self.passwordsafe_url + '/projects')
        resp.raise_for_status()
        for result in resp.json():
            if result['project']['name'] == self.project_name:
                output('found project')
                return result['project']['id']
        return None

    def build_secrets(self):
        secrets = {}
        for var in self.env_vars:
            secrets[var] = self.password(var)
        return secrets


def output(msg, *args):
    fmt = '> %s' % msg
    print fmt % args


def fatal(msg, *args):
    fmt = '*** ' + msg
    print fmt % args
    sys.exit(1)


def _get_auth_token(identity_url,
                    username,
                    password=None,
                    apikey=None,
                    rsa_token=None):
    payload = {}
    if rsa_token:
        payload = {'auth': {'RAX-AUTH:domain': {'name': 'Rackspace'},
                    'RAX-AUTH:rsaCredentials': {'tokenKey': rsa_token,
                                                'username': username}}}
    elif password:
        payload = {'auth': {'RAX-AUTH:domain': {'name': 'Rackspace'},
                    'passwordCredentials': {'password': password,
                                            'username': username}}}
    elif apikey:
        payload = {'auth': {'RAX-AUTH:domain': {'name': 'Rackspace'},
                    'RAX-KSKEY:apiKeyCredentials': {'apikey': apikey,
                                                    'username': username}}}
    else:
        fatal('rsa_token, password or apikey must be set')

    output('retrieving auth token')
    sess = requests.Session()
    sess.headers = {'content-type': 'application/json',
                    'accept': 'application/json'}
    resp = sess.post(identity_url + '/v2.0/tokens', data=json.dumps(payload))
    data = resp.json()

    err = data.get('badRequest', data.get('unauthorized'))
    if err is not None:
        fatal('%s (%d)', err['message'], err['code'])

    try:
        token = data['access']['token']['id']
        output('got token')
        return token
    except KeyError:
        fatal('unexpected response structure:\n%s', pprint.pformat(data))


def get_auth_token(identity_url,
                   sso_username=None,
                   sso_password=None,
                   token_key=None,
                   apikey=None,
                   silent=False):

    if not silent:
        if not sso_username:
            sso_username = raw_input('SSO Username: ')
        if not sso_password and not token_key:
            token_key = getpass.getpass('SSO PIN + token: ')

    return _get_auth_token(identity_url,
                           username=sso_username,
                           rsa_token=token_key,
                           password=sso_password,
                           apikey=apikey)


def main(parsed_args):
    env = {}

    # Only reaching out to external APIs if we know we should
    if not parsed_args.get('airplane'):
        if not parsed_args.get('identity_url'):
            fatal('argument identity_url is required')
        if not parsed_args.get('passwordsafe'):
            fatal('argument passwordsafe is required')

        password = parsed_args.get('password')
        username = parsed_args.get('username')
        apikey = parsed_args.get('apikey')
        auth_token = get_auth_token(
            identity_url=parsed_args.get('identity_url'),
            sso_username=username,
            sso_password=password,
            apikey=apikey
        )

        env_vars = set()
        if parsed_args.get('from_passwordsafe'):
            for item in parsed_args.get('from_passwordsafe'):
                env_vars.add(item.upper())

        ps = PasswordSafeWrapper(
            passwordsafe_url=parsed_args.get('passwordsafe'),
            project_name=parsed_args.get('project'),
            auth_token=auth_token,
            env_vars=env_vars)
        secrets = ps.secrets
        env = secrets.copy()

    overrides = parsed_args.get('override_json')

    # Overlaying anything from the parser on top of current overrides
    if parsed_args.get('override'):
        for item in parsed_args.get('override'):
            overrides[item[0].upper()] = item[1]

    env.update(overrides)

    if parsed_args.get('env_file'):
        output('saving options to file: %s' % parsed_args.get('env_file'))
        with open(parsed_args.get('env_file'), 'w') as outfile:
            json.dump(env, outfile, indent=4)

    if parsed_args.get('to_keyring'):
        for key, value in env.iteritems():
            output('setting value: %s' % key)
            # TODO: Deal with keyring
            keyring.set_password(PROJECT_NAME, key, value)
    output('saved %d options' % len(env))


def list_from_string(arg):
    """Hack to deal with loading lists from cli and from other sources"""

    # When we pull values from keychain they come back as 1 string vs multiple
    # args. Argparse handles splitting the args from the command line for us.
    # Here we are going to look for a length of 1 and assume it didn't end up
    # needing to split so we aren't casting it into a a list unnecessarily.
    split_string = arg.split()
    if len(split_string) == 1:
        return arg
    return split_string

if __name__ == '__main__':
    options = [
        config.Option('--identity_url', help='URL for identity'),
        config.Option('--username', help='identity username'),
        config.Option('--password', help='identity password'),
        config.Option('--apikey', help='identity apikey'),
        config.Option('--passwordsafe', help='URL for passwordsafe'),

        config.Option('--airplane', default=False, action='store_true',
                      help='Disable external api lookups.'),
        config.Option('--project', default=PROJECT_NAME,
                      help='Passwordsafe project name'),
        config.Option('--to-keyring', default=False, action='store_true',
                      help='Save environment to keyring'),
        config.Option('--env-file', help='Location to save env file'),
        config.Option('--override', nargs=2, action='append',
                      help='Override a specific Environment Variable.'
                           'EX: ENV_VAR VALUE'),
        config.Option('--override-json', default={}, type=json.loads,
                      help="A json string with key value pairs of environment "
                           "variables. --override takes precedence."),
        config.Option('--from-passwordsafe', nargs='*', type=list_from_string,
                      help='Name of environment variable to pull from '
                           'passwordsafe'),
        config.Option('--silent', default=False, action='store_true')
    ]

    conf = config.Config(options=options)
    parsed = conf.parse()

    try:
        main(parsed)
    except KeyboardInterrupt:
        print
        output('interrupted')
    except StandardError:
        if not parsed.get('silent'):
            import traceback
            import pdb

            traceback.print_exc()
            print 'entering debugger'
            pdb.post_mortem()
        raise