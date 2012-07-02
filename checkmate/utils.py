""" General utility functions

- handling content conversion (yaml/json)
- handling templating (Jinja2)
"""
# pylint: disable=E0611
import base64
import inspect
import json
import logging
import struct
import sys

from bottle import abort, request
import yaml
from yaml.events import AliasEvent, ScalarEvent
from yaml.parser import ParserError
from yaml.composer import ComposerError

LOG = logging.getLogger(__name__)
RESOURCES = ['deployments', 'workflows', 'blueprints', 'environments',
        'components', 'test', 'status']
STATIC = ['test']
#TODO: make this wildcards (0.password, 1.password, client_private_key,
# etc... will be returned)
DEFAULT_SENSITIVE_KEYS = ['credentials', 'password', 'apikey', 'token',
        'authtoken', 'db_password', 'ssh-private-key', 'private_key',
        'environment_private_key']


def import_class(import_str):
    """Returns a class from a string including module and class."""
    mod_str, _sep, class_str = import_str.rpartition('.')
    try:
        __import__(mod_str)
        return getattr(sys.modules[mod_str], class_str)
    except (ImportError, ValueError, AttributeError), exc:
        LOG.debug('Inner Exception: %s', exc)
        raise


def import_object(import_str, *args, **kw):
    """Returns an object including a module or module and class."""
    try:
        __import__(import_str)
        return sys.modules[import_str]
    except ImportError:
        cls = import_class(import_str)
        return cls(*args, **kw)


def resolve_yaml_external_refs(document):
    """Parses YAML and resolves any external references

    :param document: a stream object
    :returns: an iterable
    """
    anchors = []
    for event in yaml.parse(document, Loader=yaml.SafeLoader):
        if isinstance(event, AliasEvent):
            if event.anchor not in anchors:
                # Swap out local reference for external reference
                new_ref = u'checkmate-reference://%s' % event.anchor
                event = ScalarEvent(anchor=None, tag=None,
                                    implicit=(True, False), value=new_ref)
        if hasattr(event, 'anchor') and event.anchor:
            anchors.append(event.anchor)

        yield event


def read_body(request):
    """Reads request body, taking into consideration the content-type, and
    return it as a dict"""
    data = request.body
    if not data or getattr(data, 'len', -1) == 0:
        abort(400, 'No data received')
    content_type = request.get_header('Content-type', 'application/json')
    if ';' in content_type:
        content_type = content_type.split(';')[0]

    if content_type == 'application/x-yaml':
        try:
            return yaml_to_dict(data)
        except ParserError as exc:
            abort(406, "Invalid YAML syntax. Check:\n%s" % exc)
        except ComposerError as exc:
            abort(406, "Invalid YAML structure. Check:\n%s" % exc)

    elif content_type == 'application/json':
        return json.load(data)
    elif content_type == 'application/x-www-form-urlencoded':
        obj = request.forms.object
        if obj:
            result = json.loads(obj)
            if result:
                return result
        abort(406, "Unable to parse content. Form POSTs only support objects "
                "in the 'object' field")
    else:
        abort(415, "Unsupported Media Type: %s" % content_type)


def yaml_to_dict(data):
    """Parses YAML to a dict using checkmate extensions."""
    return yaml.safe_load(yaml.emit(resolve_yaml_external_refs(data),
             Dumper=yaml.SafeDumper))


def dict_to_yaml(data):
    """Parses dict to YAML using checkmate extensions."""
    return yaml.safe_dump(data, default_flow_style=False)


def write_yaml(data, request, response):
    """Write output in yaml"""
    response.add_header('content-type', 'application/x-yaml')
    return yaml.safe_dump(data, default_flow_style=False)


def write_json(data, request, response):
    """Write output in json"""
    response.set_header('content-type', 'application/json')
    return json.dumps(data, indent=4)


HANDLERS = {
    'application/x-yaml': write_yaml,
    'application/json': write_json,
    'default': write_json
    }


def write_body(data, request, response):
    """Write output with format based on accept header.
    This cycles through the global HANDLERs to match content type and then
    calls that handler. Additional handlers can be added to support Additional
    content types.
    """
    accept = request.get_header('Accept', ['application/json'])

    for content_type in HANDLERS:
        if content_type in accept:
            return HANDLERS[content_type](data, request, response)

    #Use default
    return HANDLERS['default'](data, request, response)


def extract_sensitive_data(data, sensitive_keys=None):
    """Parses the dict passed in, extracts all sensitive data into another
    dict, and returns two dicts; one without the sensitive data and with only
    the sensitive data.
    :param sensitive_keys: a list of keys considered sensitive"""

    def recursive_split(data, sensitive_keys=None):
        """Returns split of a dict or list if it contains any of the sensitive
        fields"""
        clean = None
        sensitive = None
        has_sensitive_data = False
        has_clean_data = False
        if isinstance(data, list):
            clean = []
            sensitive = []
            for value in data:
                if isinstance(value, dict):
                    c, s = recursive_split(value,
                            sensitive_keys=sensitive_keys)
                    if s is not None:
                        sensitive.append(s)
                        has_sensitive_data = True
                    else:
                        sensitive.append({})  # placeholder
                    if c is not None:
                        clean.append(c)
                        has_clean_data = True
                    else:
                        clean.append({})  # placeholder
                elif isinstance(value, list):
                    c, s = recursive_split(value,
                            sensitive_keys=sensitive_keys)
                    if s is not None:
                        sensitive.append(s)
                        has_sensitive_data = True
                    else:
                        sensitive.append([])  # placeholder
                    if c is not None:
                        clean.append(c)
                        has_clean_data = True
                    else:
                        clean.append([])
                else:
                    clean.append(value)
                    sensitive.append(None)  # placeholder
                    has_clean_data = True
        elif isinstance(data, dict):
            clean = {}
            sensitive = {}
            for key, value in data.iteritems():
                if key in sensitive_keys:
                    has_sensitive_data = True
                    sensitive[key] = value
                elif isinstance(value, dict):
                    c, s = recursive_split(value,
                            sensitive_keys=sensitive_keys)
                    if s is not None:
                        has_sensitive_data = True
                        sensitive[key] = s
                    if c is not None:
                        has_clean_data = True
                        clean[key] = c
                elif isinstance(value, list):
                    c, s = recursive_split(value,
                            sensitive_keys=sensitive_keys)
                    if s is not None:
                        has_sensitive_data = True
                        sensitive[key] = s
                    if c is not None:
                        has_clean_data = True
                        clean[key] = c
                else:
                    has_clean_data = True
                    clean[key] = value
        if has_sensitive_data:
            if has_clean_data:
                return clean, sensitive
            else:
                return None, sensitive
        else:
            if has_clean_data:
                return clean, None
            else:
                return data, None

    if sensitive_keys is None:
        sensitive_keys = DEFAULT_SENSITIVE_KEYS
    clean, sensitive = recursive_split(data, sensitive_keys=sensitive_keys)
    return clean, sensitive


def merge_dictionary(dst, src):
    """Recursive merge two dicts (vs .update which overwrites the hashes at the
        root level)
    Note: This updates dst."""
    stack = [(dst, src)]
    while stack:
        current_dst, current_src = stack.pop()
        for key in current_src:
            source = current_src[key]
            if key not in current_dst:
                current_dst[key] = source
            else:
                dest = current_dst[key]
                if isinstance(source, dict) and isinstance(dest, dict):
                    stack.append((dest, source))
                elif isinstance(source, list) and isinstance(dest, list):
                    # Make them the same size
                    r = dest[:]
                    s = source[:]
                    if len(dest) > len(source):
                        s.append([None for i in range(len(dest) -
                                len(source))])
                    elif len(dest) < len(source):
                        r.append([None for i in range(len(source) -
                                len(dest))])
                    # Merge lists
                    for index, value in enumerate(r):
                        if (not value) and s[index]:
                            r[index] = s[index]
                        elif isinstance(value, dict) and \
                                isinstance(s[index], dict):
                            stack.append((dest[index], source[index]))
                        else:
                            dest[index] = s[index]
                    current_dst[key] = r
                else:
                    current_dst[key] = source
    return dst


def is_ssh_key(key):
    """Checks if string looks like it is an ssh key"""
    if not key:
        return False
    if not isinstance(key, basestring):
        return False
    if not key.startswith('ssh-rsa AAAAB3NzaC1yc2EA'):
        return False
    if ' ' not in key:
        return False
    parts = key.split()
    if len(parts) < 2:
        return False
    if len(parts) > 2:
        key_type, key_string, comment = parts[0:3]
    else:
        key_type, key_string = parts[0:2]
    try:
        data = base64.decodestring(key_string)
    except:
        return False
    int_len = 4
    str_len = struct.unpack('>I', data[:int_len])[0]  # this should return 7
    if str_len != 7:
        return False
    if data[int_len:int_len + str_len] == 'ssh-rsa':
        return True
    return False


def get_source_body(function):
    """Gets the body of a function (i.e. no definition line, and unindented"""
    # Unindent
    lines = inspect.getsource(function).split('\n')[1:]
    indent = len(lines[0]) - len(lines[0].lstrip())
    for index, line in enumerate(lines):
        lines[index] = line[indent:]
    return '\n'.join(lines)


def with_tenant(fn):
    """A function decorator that a context tenant_id is passed in to the
    decorated function as a kwarg"""
    def wrapped(*args, **kwargs):
        if kwargs and kwargs.get('tenant_id'):
            # Tenant ID is being passed in
            return fn(*args, **kwargs)
        else:
            return fn(*args, tenant_id=request.context.tenant, **kwargs)
    return wrapped
