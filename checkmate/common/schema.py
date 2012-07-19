""" This files contains initial schema validation and utilities

It is currently used for debugging and so is limited to known reqoiurce types,
interfaces, and such. The intent is to broaden it once we have stab lized the
schema.

"""
import logging

from checkmate.utils import yaml_to_dict

LOG = logging.getLogger(__name__)

INTERFACE_SCHEMA = yaml_to_dict("""
      mysql:
        fields:
          username:
            type: string
            required: true
          password:
            type: string
            required: true
          hostname:
            type: string
            required: true
          port:
            type: int
            required: true
            default: 3306
          database:
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
    """)

INTERFACE_TYPES = INTERFACE_SCHEMA.keys()

RESOURCE_TYPES = ['compute', 'database', 'wordpress', 'php5', 'load-balancer',
        'endpoint', 'host', 'application',
        'widget', 'gadget']  # last two for testing

RESOURCE_SCHEMA = ['id', 'name', 'provider', 'relations', 'hosted_on', 'hosts',
        'type', 'component', 'dns-name', 'instance', 'flavor', 'image', 'disk',
        'region']

DEPLOYMENT_SCHEMA = ['id', 'name', 'blueprint', 'environment', 'inputs',
        'includes', 'resources', 'settings']

COMPONENT_SCHEMA = ['id', 'options', 'requires', 'provides', 'summary',
        'dependencies', 'version', 'is', 'role']


def validate_catalog(obj):
    """Validates provider catalog"""
    errors = []
    if obj:
        for key, value in obj.iteritems():
            if not (key in RESOURCE_TYPES or key == 'lists'):
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

# The list of 'allowed' names in options, resources, and relations in checkmate
# and the other possible aliases for them. Checkmate will convert aliases into
# the canonical name
# Naming conventions being used now:
# - use underscores for separtors
# - all lowercase
# - full names (ex. database, not db). Except for id.

ALIASES = {
        'username': ['user'],
        'password': ['pass'],
        'private': ['priv'],
        'public': ['pub'],
        'key': [],
        'nonce': [],
        'path': [],
        'server': ['srv', 'srvr'],
        'host': ['hostname'],
        'authentication': ['auth'],
        'directory': ['dir'],
        'destination': ['dest'],
        'database': ['db'],
        'configuration': ['conf'],
        'certificate': ['cert'],
        'memory': ['mem'],
        'id': [],
        'status': [],
        'region': [],
        'operating_system': ['os'],
    }


def translate(name):
    """Convert any aliases to the canonical names as per ALIASES map

    Canonicalizes composite names to be separated by underscores.
    Keeps path separators intack (name/alias becomes name/canonical_name)
    """
    # Check if is already canonical
    if name in ALIASES or not name:
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
    if any((c in name) for c in word_seps):
        chars = list(name)
        words = ''.join([' ' if o in word_seps else o for o in chars]
                ).split(' ')
        for index, word in enumerate(words):
            words[index] = translate(word) or ''
        return '_'.join(words)

    LOG.info("Unrecognized name: %s" % name)
