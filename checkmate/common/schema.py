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

"""Schema validation and utilities.

Initial implementation. Currently used for debugging and so is limited to known
resource types, interfaces, and such. The intent is to broaden it once we have
stabilized theschema.
"""

import logging

from voluptuous import (
    All,
    Any,
    Extra,
    Invalid,
    Length,
    MultipleInvalid,
    Schema,
)

from checkmate.inputs import Input
from checkmate.utils import yaml_to_dict

LOG = logging.getLogger(__name__)

RESOURCE_TYPES = [
    'application',
    'cache',
    'compute',
    'database',
    'directory',
    'dns',
    'object-store',
    'host',
    'load-balancer',
    'mail-relay',
    'web',
    'monitoring',
    'storage',

    # TODO(zns): All below to be removed (including testing ones)
    'wordpress',
    'php5',
    'endpoint',  # not sure what this was used for

    # for testing
    'widget',
    'gadget',
]


class RequireOneInvalid(Invalid):

    """At least one of a required set of keys is missing from a dict."""


def RequireOne(keys):
    """Validate that at least on of the supplied keys exists on a dict."""
    def check(val):
        if any(([k in val for k in keys])):
            return
        raise RequireOneInvalid("one of '%s' is required" % ', '.join(keys))
    return check


def DictOf(schema):
    """Validate that all values in a dict adhere to the supplied schema."""
    def check(val):
        if not isinstance(val, dict):
            raise Invalid('value not a dict')
        errors = []
        for value in val.itervalues():
            try:
                schema(value)
            except MultipleInvalid as exc:
                errors.extend(exc.errors)
            except Invalid as exc:
                errors.append(exc)
        if errors:
            raise MultipleInvalid(errors)

    return check


FUNCTION_SCHEMA = Schema({
    'from': list,
    'if': dict,
    'if-not': dict,
    'or': list,
    'and': list,
    'exists': dict,
    'not-exists': dict,
    'value': Any(str, dict)
})

ENDPOINT_SCHEMA = Schema({
    'resource_type': Any(*RESOURCE_TYPES),
    'interface': Any(str, dict),
    'relation': Any('reference', 'host'),
    'constraints': [dict],
    'id': str
})


def check_schema(schema, value):
    """Test that a value abides by a specific schema."""
    try:
        schema(value)
        return True
    except MultipleInvalid:
        return False


def Shorthand(msg=None):
    """Coerce a shorthand connection point value to longhand."""
    def check(entry):
        if isinstance(entry, dict) and len(entry) == 1:
            key, value = entry.items()[0]
            if isinstance(value, dict):
                if check_schema(ENDPOINT_SCHEMA, value):
                    # index + endpoint (long form)
                    return dict(id=key, **value)
                elif check_schema(FUNCTION_SCHEMA, value):
                    # shorthand with function
                    return {'resource_type': key, 'interface': value}
                else:
                    raise Invalid('not a valid endpoint')
            # shorthand (type: interface)
            return {'resource_type': key, 'interface': value}
        return entry
    return check


RESOURCE_METADATA = yaml_to_dict("""
    application:
      label: Application
      description: An application that is installed on a compute resource
    compute:
      label: Servers
      description: A server
    """)

INTERFACE_SCHEMA = yaml_to_dict("""
      bar:
        description: for testing
      dns_udp:
      dns_tcp:
      foo:
        description: for testing
      ftp:
      gluster:
      http:
        is: url
        constraint:
        - protocol: [http, https]
      https:
      host:
         options:
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
      imaps:
      imapv2:
      imapv3:
      imapv4:
      ldap:
      ldaps:
      linux:
        description: ssh or shell interface to linux
        options:
          protocol:
            default: shell
            type: string
            options:
            - shell
            - ssh
      # community cares about this. The software is memcached, but I speak
      # memcache
      memcache:
      mongodb:
      mysql:
        options:
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
      new-relic:
      php:
      pop3:
      pop3s:
      postgres:
      proxy:
        description: A proxy for other protocols; i.e. a load balancer or IDS
        options:
          protocol:
             type: string
             description: the protocol being proxied
             required: true

      rackspace-cloud-monitoring:
      redis:
      rdp:
      sftp:
      smtp:
      ssh:
      tcp_client_first:
      tcp_stream:
      tcp:
      udp:
      udp_stream:
      url:
        options:
          protocol:
            type: string
            required: true
            default: http
            constraints:
            - in:
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
      varnish:
      vip:
         options:
           ip:
             type: string
             required: true
           private_ip:
             type: string,
             required: false
           public_ip:
             type: string
      windows:
        description: wmi and shell interface to Windows
        options:
          protocol:
            default: wmi
            type: string
            options:
            - shell
            - wmi
    """)

INTERFACE_TYPES = INTERFACE_SCHEMA.keys()


OPTION_SCHEMA = [
    'constrains',
    'constraints',
    'default',
    'description',
    'display-hints',
    'display-output',
    'help',
    'label',
    'required',
    'source_field_name',
    'type',
    'unit',
]

# Add parts used internally by providers, but not part of the public schema
OPTION_SCHEMA_INTERNAL = OPTION_SCHEMA + [
    'source',
    'source_field_name',
]

OPTION_SCHEMA_URL = [
    'certificate',
    'hostname',
    'intermediate_key',
    'netloc',
    'path',
    'port',
    'protocol',
    'private_key',
    'scheme',
    'url',
]

OPTION_TYPES = [
    'string',
    'integer',
    'boolean',
    'url',
    'password',
    'text',
]


def schema_from_list(keys_list):
    """Generates a schema from a list of keys."""
    return Schema(dict((key, object) for key in keys_list))


ENDPOINTS_SCHEMA = [Shorthand()]
COMPONENT_STRICT_SCHEMA_DICT = {
    'id': All(str, Length(min=3, max=32)),
    'name': str,
    'is': Any(*RESOURCE_TYPES),
    'provider': str,
    'options': DictOf(schema_from_list(OPTION_SCHEMA)),
    'requires': ENDPOINTS_SCHEMA,
    'provides': ENDPOINTS_SCHEMA,
    'uses': ENDPOINTS_SCHEMA,
    'summary': str,
    'display_name': str,
    'version': str,
    'roles': [str],
    'properties': dict,
    'meta-data': dict,
}
COMPONENT_SCHEMA = All(
    Schema(COMPONENT_STRICT_SCHEMA_DICT),
    RequireOne(['id', 'name'])
)

# Loose schema for compatibility and loose validation
COMPONENT_LOOSE_SCHEMA_DICT = COMPONENT_STRICT_SCHEMA_DICT.copy()
COMPONENT_LOOSE_SCHEMA_DICT.update({
    'role': str,
    'source_name': str,
    'type': Any(*RESOURCE_TYPES),
    'resource_type': Any(*RESOURCE_TYPES),
    Extra: object,  # To support provider-specific values
})
COMPONENT_LOOSE_SCHEMA = Schema(COMPONENT_LOOSE_SCHEMA_DICT)

SERVICE_SCHEMA = Schema({
    'component': COMPONENT_SCHEMA,
    'relations': [Shorthand()],
    'constraints': list,
})

BLUEPRINT_SCHEMA = Schema({
    'id': object,
    'name': object,
    'services': dict,  # DictOf(SERVICE_SCHEMA),
    'options': object,
    'resources': object,
    'meta-data': object,
    'description': object,
    'display-outputs': object,
    'documentation': object,
    'version': object,
    'source': object,
})

WORKFLOW_SCHEMA = [
    'attributes',
    'id',
    'last_task',
    'task_tree',
    'tenantId',
    'success',
    'wf_spec',
    'workflow',
]

DEPLOYMENT_SCHEMA_DICT = {
    'id': object,
    'name': object,
    'blueprint': Any(BLUEPRINT_SCHEMA, None),
    'resources': object,
    'inputs': object,
    'environment': object,
    'operation': object,

    'display-outputs': object,
    'workflow': object,
    'status': object,
    'created': object,
    'tenantId': object,
    'error-messages': object,
    'live': object,
    'plan': object,
    'operations-history': object,
    'created-by': object,
    'secrets': object,
    'meta-data': object,  # Used to store/show miscellaneous data
    'check-limit-results': object,
    'check-access-results': object,
    'includes': object,  # temp store for YAML-referenced parts (then removed)
}
DEPLOYMENT_SCHEMA = Schema(DEPLOYMENT_SCHEMA_DICT, required=False)


SCHEMA_MAPS = {
    'checkmate.component': COMPONENT_SCHEMA,
    'checkmate.blueprints.blueprint': BLUEPRINT_SCHEMA,
    'checkmate.deployment': DEPLOYMENT_SCHEMA,
}


def get_schema(name):
    """Return the schema that matches the supplied module name."""
    if name in SCHEMA_MAPS:
        return SCHEMA_MAPS[name]
    return {}


def validate_catalog(obj):
    """Validate provider catalog."""
    errors = []
    if obj:
        for key, value in obj.iteritems():
            if key == 'lists':
                pass
            elif key in RESOURCE_TYPES:
                for id_, component in value.iteritems():
                    if 'id' not in component and 'name' not in component:
                        component['id'] = id_
                    errors.extend(validate(component, COMPONENT_SCHEMA) or [])
            else:
                errors.append("'%s' not a valid value. Only %s, 'lists' "
                              "allowed" % (key, ', '.join(RESOURCE_TYPES)))
    return errors


def validate(obj, schema):
    """Validate an object.

    :param obj: a dict of the object to validate
    :param schema: a schema to validate against (usually from this file)

    This is a simple, initial attempt at validation.
    """
    errors = []
    if obj:
        if schema:
            if isinstance(schema, list):
                LOG.debug("Converting list to Schema: %s", schema)
                schema = schema_from_list(schema)
            try:
                schema(obj)
            except MultipleInvalid as exc:
                for error in exc.errors:
                    errors.append(str(error))
            except Invalid as exc:
                errors.append(str(exc))
    return errors


def validate_inputs(deployment):
    """Validate deployment inputs."""
    errors = []
    if deployment:
        inputs = deployment.get('inputs') or {}
        blueprint = deployment.get('blueprint') or {}
        options = blueprint.get('options') or {}
        for key, value in inputs.iteritems():
            if key == 'blueprint':
                for key2, value2 in value.iteritems():
                    option = options.get(key2)
                    if not option:
                        pass
                    elif option.get('type') == 'url':
                        errors.extend(validate_url_input(key2, value2))
                    else:
                        errors.extend(validate_input(key2, value2))
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
    """Validate deployment inputs in a type hierarchy
    This is the structure under inputs/services and inputs/providers.
    """
    errors = []
    if inputs:
        if isinstance(inputs, dict):
            for key, value in inputs.iteritems():
                if key not in RESOURCE_TYPES:
                    errors.append("Invalid type '%s' in inputs" % key)
                else:
                    if isinstance(value, dict):
                        for key2, value2 in value.iteritems():
                            errors.extend(validate_input(key2, value2))
                    else:
                        errors.append("Input '%s' is not a key/value pair" %
                                      value)
        else:
            errors.append("Input '%s' is not a key/value pair" % inputs)
    return errors


def validate_input(key, value):
    """Validate a deployment input."""
    errors = []
    if value:
        if isinstance(value, dict):
            errors.append("Option '%s' should be a scalar" % key)

    return errors


def validate_url_input(key, value):
    """Validate a deployment input of type url."""
    errors = []
    if value:
        if isinstance(value, dict):
            errors.extend(validate(value, OPTION_SCHEMA_URL))
        elif not isinstance(value, basestring):
            errors.append("Option '%s' should be a string or valid url "
                          "mapping. It is a '%s' which is not valid" %
                          (key, value.__class__.__name__))

    return errors


def validate_option(key, option):
    """Validate a blueprint option."""
    errors = []
    if option:
        if isinstance(option, dict):
            errors = validate(option, OPTION_SCHEMA)
            option_type = option.get('type')
            if option_type not in OPTION_TYPES:
                errors.append("Option '%s' type is invalid. It is '%s' and "
                              "the only allowed types are: %s" %
                              (key, option_type, OPTION_TYPES))
        else:
            errors.append("Option '%s' must be a map" % key)
    return errors


def validate_options(options):
    """Validate a blueprint's options."""
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
    """Convert any aliases to the canonical names as per ALIASES map.

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
        segments = ''.join([' ' if o in path_seps else o for o in chars])\
            .split(' ')
        for index, segment in enumerate(segments):
            segments[index] = translate(segment) or ''
        return path_separator.join(segments)

    # Check if composite (made up of a number of words together)
    word_seps = '.-_'
    recognized = False
    if any((c in name) for c in word_seps):
        chars = list(name)
        words = ''.join([' ' if o in word_seps else o for o in chars])\
            .split(' ')
        for index, word in enumerate(words):
            words[index] = translate(word) or ''
        # FIXME: this breaks some recipes used in chef components, so we won't
        # return it, but we also won't log it until we fix this.
        recognized = True
        #return '_'.join(words)

    if not recognized:
        LOG.debug("Unrecognized name: %s", name)
    return name


def translate_dict(data):
    """Translate dictionary keys to canonical checkmate names.

    :returns: translated dict
    """
    if data:
        results = {}
        for key, value in data.iteritems():
            canonical = translate(key)
            if key != canonical:
                LOG.debug("Translating '%s' to '%s'", key, canonical)
            results[canonical] = value
        return results
