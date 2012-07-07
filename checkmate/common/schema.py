# This files contains initial schema validation and utilities
from checkmate.utils import yaml_to_dict


INTERFACES = yaml_to_dict("""
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
      website:
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
    """)

DEPLOYMENT_FIELDS = ['id', 'name', 'blueprint', 'environment', 'inputs',
        'includes']

COMPONENT_FIELDS = ['id', 'options', 'requires', 'provides', 'summary',
        'dependencies', 'revision', 'is']


def validate(obj, schema):
    """Validates an object

    This is a simple, initial attempt at validation"""
    errors = []
    if obj:
        for key, value in obj.iteritems():
            if key not in schema:
                errors.append("'%s' not a valid value. Only %s allowed" % (key,
                        ', '.join(schema)))
    return errors
