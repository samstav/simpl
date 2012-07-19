""" This files contains initial schema validation and utilities

It is currently used for debugging and so is limited to known reqoiurce types,
interfaces, and such. The intent is to broaden it once we have stab lized the
schema.

"""
from checkmate.utils import yaml_to_dict


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
