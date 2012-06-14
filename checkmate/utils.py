""" General utility functions

- handling content conversion (yaml/json)
- handling templating (Jinja2)
"""
# pylint: disable=E0611
import base64
import inspect
import json
import logging
import os
import struct
import sys

from bottle import abort, request
from jinja2 import BaseLoader, TemplateNotFound, Environment
import yaml
from yaml.events import AliasEvent, ScalarEvent

LOG = logging.getLogger(__name__)
RESOURCES = ['deployments', 'workflows', 'static', 'blueprints',
             'environments', 'components', 'test', 'status']
DEFAULT_SENSITIVE_KEYS = ['credentials', 'password', 'apikey', 'token',
        'authtoken', 'db_password', 'ssh-private-key']


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


def get_template_name_from_path(path):
    """ Returns template name from request path"""
    name = 'default'
    if path:
        if path[0] == '/':
            parts = path[1:].split('/')  # normalize to always not include first path
        else:
            parts = path.split('/')
        if len(parts) > 0 and parts[0] not in RESOURCES:
            # Assume it is a tenant (and remove it from our evaluation)
            parts = parts[1:]

        # IDs are 2nd or 4th: /[type]/[id]/[type2|action]/[id2]/action
        if len(parts) == 1:
            # Resource
            name = "%s" % parts[0]
        elif len(parts) == 2:
            # Single resource
            name = "%s" % parts[0][0:-1]  # strip s
        elif len(parts) == 3:
            if parts[2].startswith('+'):
                # Action
                name = "%s.%s" % (parts[0][0:-1], parts[2][1:])
            elif parts[2] in ['tasks']:
                # Subresource
                name = "%s.%s" % (parts[0][0:-1], parts[2])
            else:
                # 'status' and the like
                name = "%s.%s" % (parts[0][0:-1], parts[2])
        elif len(parts) > 3:
            if parts[2] in ['tasks']:
                # Subresource
                name = "%s.%s" % (parts[0][0:-1], parts[2][0:-1])
            else:
                # 'status' and the like
                name = "%s.%s" % (parts[0][0:-1], parts[2])
    LOG.debug("Template for '%s' returned as '%s'" % (path, name))
    return name


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
    if content_type == 'application/x-yaml':
        return yaml.safe_load(yaml.emit(resolve_yaml_external_refs(data),
                         Dumper=yaml.SafeDumper))
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


def write_body(data, request, response):
    """Write output with format based on accept header. json is default"""
    accept = request.get_header('Accept', ['application/json'])

    # YAML
    if 'application/x-yaml' in accept:
        response.add_header('content-type', 'application/x-yaml')
        return yaml.safe_dump(data, default_flow_style=False)

    # HTML
    if 'text/html' in accept:
        response.add_header('content-type', 'text/html')

        name = get_template_name_from_path(request.path)

        class MyLoader(BaseLoader):
            def __init__(self, path):
                self.path = path

            def get_source(self, environment, template):
                path = os.path.join(self.path, template)
                if not os.path.exists(path):
                    raise TemplateNotFound(template)
                mtime = os.path.getmtime(path)
                with file(path) as f:
                    source = f.read().decode('utf-8')
                return source, path, lambda: mtime == os.path.getmtime(path)
        env = Environment(loader=MyLoader(os.path.join(os.path.dirname(
            __file__), 'static')))

        def do_prepend(value, param='/'):
            """
            Prepend a string if the passed in string exists.

            Example:
            The template '{{ root|prepend('/')}}/path';
            Called with root undefined renders:
                /path
            Called with root defined as 'root' renders:
                /root/path
            """
            if value:
                return '%s%s' % (param, value)
            else:
                return ''
        env.filters['prepend'] = do_prepend
        env.json = json
        tenant_id = request.get('HTTP_X_TENANT_ID')
        try:
            template = env.get_template("%s.template" % name)
            return template.render(data=data, source=json.dumps(data,
                    indent=2), tenant_id=tenant_id)
        except StandardError as exc:
            LOG.exception(exc)
            try:
                template = env.get_template("default.template")
                return template.render(data=data, source=json.dumps(data,
                        indent=2), tenant_id=tenant_id)
            except StandardError as exc2:
                LOG.exception(exc2)
                pass  # fall back to JSON

    #JSON (default)
    response.set_header('content-type', 'application/json')
    return json.dumps(data, indent=4)


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
                    c, s = recursive_split(value, sensitive_keys=sensitive_keys)
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
                    c, s = recursive_split(value, sensitive_keys=sensitive_keys)
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
                    c, s = recursive_split(value, sensitive_keys=sensitive_keys)
                    if s is not None:
                        has_sensitive_data = True
                        sensitive[key] = s
                    if c is not None:
                        has_clean_data = True
                        clean[key] = c
                elif isinstance(value, list):
                    c, s = recursive_split(value, sensitive_keys=sensitive_keys)
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
    """Assures that a context tenant_id is passed in to called function"""
    def wrapped(*args, **kwargs):
        if kwargs and kwargs.get('tenant_id'):
            # Tenant ID is being passed in
            return fn(*args, **kwargs)
        else:
            return fn(*args, tenant_id=request.context.tenant, **kwargs)
    return wrapped
