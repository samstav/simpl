""" This files contains initial schema validation and utilities

It is currently used for debugging and so is limited to known resource types,
interfaces, and such. The intent is to broaden it once we have stabilized the
schema.

"""
import logging

from checkmate.inputs import Input
from checkmate.utils import yaml_to_dict

LOG = logging.getLogger(__name__)

RESOURCE_METADATA = yaml_to_dict("""
    application:
      label: Application
      description: An application that is installed on a compute resource
      help-text: |
        sd.jhsdflkgjhsdfg
        sdfg;kjhsdfg
        sdfgsdfg
        sdfgsdfg
        dfgsdfg
    compute:
      label: Servers
      description: A server
      help-text: |
        sd.jhsdflkgjhsdfg
        sdfg;kjhsdfg
        sdfgsdfg
    """)

INTERFACE_SCHEMA = yaml_to_dict("""
      host:
         fields:
           id:
             type: string
             required: true
           status:
             type: string
             required: true
           region:
             type: string
             required: true
           ip:
             type: string
             required: true
           private_ip:
             type: string,
             required: false
           public_ip:
             type: string
             required: false
           password:
             type: string
             required: false
      mysql:
        fields:
          username:
            type: string
            required: true
          password:
            type: string
            required: true
          host:
            type: string
            required: true
          port:
            type: int
            required: true
            default: 3306
          database_name:
            type: string
            required: false
      mssql:
      http:
        is: url
        constraint:
        - protocol: [http, https]
      url:
        fields:
          protocol:
            type: string
            required: true
            default: http
            options:
            - http
            - https
            - ldap
            - ftp
            - ssh
          path:
            type: string
            required: false
            default: /
          host:
            description: resolveable name or IP address of host
            type: string
            required: true
          port:
            type: int
            required: true
            default: 80
          username:
            type: string
            required: false
          password:
            type: string
            required: false
      linux:
        description: ssh or shell interface to linux
        fields:
          protocol:
            default: shell
            type: string
            options:
            - shell
            - ssh
      windows:
        description: wmi and shell interface to Windows
        fields:
          protocol:
            default: wmi
            type: string
            options:
            - shell
            - wmi
      foo:
        description: for testing
      bar:
        description: for testing
      ftp:
      sftp:
      https:
      ldap:
      ldaps:
      smtp:
      pop3:
      pop3s:
      imaps:
      imapv2:
      imapv3:
      imapv4:
      dns_udp:
      dns_tcp:
      rdp:
      ssh:
      udp:
      udp_stream:
      tcp_client_first:
      tcp:
      proxy:
        description: A proxy for other protocols; i.e. a load balancer or IDS
        fields:
          protocol:
             type: string
             description: the protocol being proxied
             required: true
    """)

INTERFACE_TYPES = INTERFACE_SCHEMA.keys()

RESOURCE_TYPES = ['compute', 'database', 'wordpress', 'php5', 'load-balancer',
        'endpoint', 'host', 'application',
        'widget', 'gadget']  # last two for testing

RESOURCE_SCHEMA = ['id', 'index', 'name', 'provider', 'relations', 'hosted_on',
        'hosts', 'type', 'component', 'dns-name', 'instance', 'flavor',
        'image', 'disk', 'region', 'service', 'status']

BLUEPRINT_SCHEMA = ['id', 'name', 'services', 'options', 'resources',
                    'meta-data', 'description', 'display-outputs',
                    'documentation', 'version']

DEPLOYMENT_SCHEMA = ['id', 'name', 'blueprint', 'environment', 'inputs',
        'includes', 'resources', 'workflow', 'status', 'created',
        'tenantId', 'errmessage', 'display-outputs', 'operation']

COMPONENT_SCHEMA = ['id', 'options', 'requires', 'provides', 'summary',
        'dependencies', 'version', 'is', 'role', 'roles', 'source_name']

OPTION_SCHEMA = [
                 'label',
                 'default',
                 'help',
                 'choice',
                 'description',
                 'required',
                 'type',
                 'constrains',
                 'constraints',
                 'display-hints',
                ]
# Add parts used internally by providers, but not part of the public schema
OPTION_SCHEMA_INTERNAL = OPTION_SCHEMA + [
                 'source',
                 'source_field_name',
                ]

OPTION_SCHEMA_URL = [
    'url',
    'protocol',
    'scheme',
    'netloc',
    'hostname',
    'port',
    'path',
    'certificate',
    'private_key',
    'intermediate_key',
]

OPTION_TYPES = [
                'string',
                'integer',
                'boolean',
                'url',
                'password',
                'text',
               ]

WORKFLOW_SCHEMA = ['id', 'attributes', 'last_task', 'task_tree', 'workflow',
        'success', 'wf_spec', 'tenantId']


def validate_catalog(obj):
    """Validates provider catalog"""
    errors = []
    if obj:
        for key, value in obj.iteritems():
            if key == 'lists':
                pass
            elif key in RESOURCE_TYPES:
                for instance in value.values():
                    errors.extend(validate(instance, COMPONENT_SCHEMA) or [])
            else:
                errors.append("'%s' not a valid value. Only %s, 'lists' "
                        "allowed" % (key, ', '.join(RESOURCE_TYPES)))
    return errors


def validate(obj, schema):
    """Validates an object

    :param obj: a dict of the object to validate
    :param schema: a schema to validate against (usually from this file)

    This is a simple, initial attempt at validation"""
    errors = []
    if obj:
        if schema:
            for key, value in obj.iteritems():
                if key not in schema:
                    errors.append("'%s' not a valid value. Only %s allowed" %
                                  (key, ', '.join(schema)))
    return errors


def validate_inputs(deployment):
    """Validates deployment inputs"""
    errors = []
    if deployment:
        inputs = deployment.get('inputs') or {}
        blueprint = deployment.get('blueprint') or {}
        options = blueprint.get('options') or {}
        for key, value in inputs.iteritems():
            if key == 'blueprint':
                for k, v in value.iteritems():
                    option = options.get(k)
                    if not option:
                        pass
                    elif option.get('type') == 'url':
                        errors.extend(validate_url_input(k, v))
                    else:
                        errors.extend(validate_input(k, v))
            elif key == 'services':
                for service_name, service_input in value.iteritems():
                    if service_name not in deployment['blueprint']['services']:
                        errors.append("Invalid service name in inputs: %s" %
                                      service_name)
                    errors.extend(validate_type_inputs(service_input))
            elif key == 'providers':
                for provider_key, provider_input in value.iteritems():
                    if provider_key not in deployment['environment'][
                            'providers']:
                        errors.append("Invalid provider key in inputs: %s" %
                                      provider_key)
                    errors.extend(validate_type_inputs(provider_input))
            else:
                if not isinstance(value, int):
                    value = Input(value)
                errors.extend(validate_input(key, value))  # global input

    return errors


def validate_type_inputs(inputs):
    """Validates deployment inputs in a type hierarchy

    This is the structure under inputs/services and inputs/providers"""
    errors = []
    if inputs:
        if isinstance(inputs, dict):
            for key, value in inputs.iteritems():
                if key not in RESOURCE_TYPES:
                    errors.append("Invalid type '%s' in inputs" % key)
                else:
                    if isinstance(value, dict):
                        for k, v in value.iteritems():
                            errors.extend(validate_input(k, v))
                    else:
                        errors.append("Input '%s' is not a key/value pair" %
                                      value)
        else:
            errors.append("Input '%s' is not a key/value pair" % inputs)
    return errors


def validate_input(key, value):
    """Validates a deployment input"""
    errors = []
    if value:
        if isinstance(value, dict):
            errors.append("Option '%s' should be a scalar" % key)

    return errors


def validate_url_input(key, value):
    """Validates a deployment input of type url"""
    errors = []
    if value:
        if isinstance(value, dict):
            errors.extend(validate(value, OPTION_SCHEMA_URL))
        elif not isinstance(value, basestring):
            errors.append("Option '%s' should be a string or valid url "
                          "mapping. It is a '%s' which is not valid" % (
                          key, value.__class__.__name__))

    return errors


def validate_option(key, option):
    """Validates a blueprint option"""
    errors = []
    if option:
        if isinstance(option, dict):
            errors = validate(option, OPTION_SCHEMA)
            option_type = option.get('type')
            if option_type not in OPTION_TYPES:
                errors.append("Option '%s' type is invalid. It is '%s' and "
                              "the only allowed types are: %s" % (key,
                              option_type, OPTION_TYPES))
        else:
            errors.append("Option '%s' must be a map" % key)
    return errors


def validate_options(options):
    """Validates a blueprint's options"""
    errors = []
    if options:
        if isinstance(options, dict):
            for key, option in options.items():
                option_errors = validate_option(key, option)
                if option_errors:
                    errors.extend(option_errors)
        else:
            errors.append("Blueprint `options` key must be a map")
    return errors


# The list of 'allowed' names in options, resources, and relations in checkmate
# and the other possible aliases for them. Checkmate will convert aliases into
# the canonical name
# Naming conventions being used now:
# - use underscores for separtors
# - all lowercase
# - full names (ex. database, not db). Except for id.

ALIASES = {
        'apache': ['apache2'],
        'authentication': ['auth'],
        'configuration': ['conf'],
        'database': ['db'],
        'description': ['desc'],
        'destination': ['dest'],
        'directory': ['dir'],
        'drupal': [],
        'etherpad': [],
        'host': ['hostname'],
        'id': [],
        'ip': [],
        'instance': [],
        'key': [],
        'maximum': ['max'],
        'memory': ['mem'],
        'mysql': [],
        'name': [],
        'nonce': [],
        'operating_system': ['os'],
        'path': [],
        'password': ['pass'],
        'prefork': [],
        'region': [],
        'server': ['srv', 'srvr'],
        'source': ['src'],
        'ssh': [],
        'status': [],
        'username': [],
        'user': [],
        'wordpress': ['wp'],
        'worker': [],
    }

# Add items we come across frequently just to minimize log noise
ALIASES.update({
        'access': [],
        'address': [],
        'allowed': [],
        'apt': [],
        'aws': [],
        'awwbomb': [],
        'back': [],
        'bin': [],
        'bind': [],
        'bluepill': [],
        'bucket': [],
        'buffer': [],
        'build': [],
        'cache': [],
        'cert': [],
        'certificate': [],
        'checkmate': [],
        'chef': [],
        'client': [],
        'connection': ['connections'],
        'contact': [],
        'container': [],
        'create': [],
        'data': [],
        'day': ['days'],
        'default': [],
        'dmg': [],
        'domain': [],
        'ec2': [],
        'enabled': [],
        'essential': [],
        'expire': [],
        'firewall': [],
        'gzip': [],
        'handler': [],
        'hash': [],
        'heap': [],
        'holland': [],
        'iptables': [],
        'keepalive': [],
        'level': [],
        'listen': [],
        'lite': [],
        'log': ['logs'],
        'lsyncd': [],
        'memcached': [],
        'monit': [],
        'net': [],
        'nginx': [],
        'nodejs': [],
        'npm': [],
        'ohai': [],
        'open': [],
        'openssl': [],
        'php': [],
        'php5': [],
        'port': ['ports'],
        'postfix': [],
        'postgresql': [],
        'prefix': [],
        'private': [],
        'process': ['processes'],
        'public': [],
        'read': [],
        'root': [],
        'runit': [],
        'size': [],
        'secure': [],
        'self': [],
        'service': [],
        'site': [],
        'slave': ['slaves'],
        'ssl': [],
        'suhosin': [],
        'table': [],
        'timeout': [],
        'tunable': [],
        'type': ['types'],
        'ufw': [],
        'varnish': [],
        'version': [],
        'vsftpd': [],
        'wait': [],
        'windows': [],
        'write': [],
        'xfs': [],
        'xml': [],
        'yum': [],
    })


def translate(name):
    """Convert any aliases to the canonical names as per ALIASES map

    Canonicalizes composite names to be separated by underscores.
    Keeps path separators intack (name/alias becomes name/canonical_name)
    @deprecated: this prevents us from using third party chef-based
                 components without modification
    """
    # Check if is already canonical
    if name in ALIASES or not name or not isinstance(name, basestring):
        return name
    # Check if exists as-is in aliases
    for canonical, alternatives in ALIASES.iteritems():
        if name in alternatives:
            return canonical

    # Check if path
    path_separator = '/'
    path_seps = '/'
    if any((c in name) for c in path_seps):
        chars = list(name)
        segments = ''.join([' ' if o in path_seps else o for o in chars]
                ).split(' ')
        for index, segment in enumerate(segments):
            segments[index] = translate(segment) or ''
        return path_separator.join(segments)

    # Check if composite (made up of a number of words together)
    word_seps = '.-_'
    recognized = False
    if any((c in name) for c in word_seps):
        chars = list(name)
        words = ''.join([' ' if o in word_seps else o for o in chars]
                ).split(' ')
        for index, word in enumerate(words):
            words[index] = translate(word) or ''
        # FIXME: this breaks some recipes used in chef components, so we won't
        # return it, but we also won't log it until we fix this.
        recognized = True
        #return '_'.join(words)

    if not recognized:
        LOG.debug("Unrecognized name: %s" % name)
    return name


def translate_dict(data):
    """Translates dictionary keys to canonical checkmate names

    :returns: translated dict
    """
    if data:
        results = {}
        for key, value in data.iteritems():
            canonical = translate(key)
            if key != canonical:
                LOG.debug("Translating '%s' to '%s'" % (key, canonical))
            results[canonical] = value
        return results
