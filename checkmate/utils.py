# pylint: disable=C0302,E1101
# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
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

"""General utility functions.

- handling content conversion (yaml/json)
"""

import base64
import collections
import copy
import inspect
import json
import logging.config
import os
import re
import shlex
import shutil
import string
import struct
import subprocess as subprc
import sys
import time
import traceback as traceback_module
import urlparse
import uuid

import bottle
from Crypto.Random import random
import errno
from eventlet.green import threading
import functools
import yaml
from yaml import composer
from yaml import events
from yaml import parser
from yaml import scanner

from checkmate.common import codegen
from checkmate import exceptions as cmexc


LOG = logging.getLogger(__name__)
DEFAULT_SENSITIVE_KEYS = [
    'credentials',
    'apikey',
    'error-traceback',
    'error-string',
    re.compile("(?:(?:auth)|(?:api))?[-_ ]?token$"),
    re.compile("priv(?:ate)?[-_ ]?key$"),
    re.compile('password$'),
    re.compile('^password'),
]


def match_celery_logging(logger):
    """Match celery log level."""
    if logger.level < int(os.environ.get('CELERY_LOG_LEVEL', logger.level)):
        logger.setLevel(int(os.environ.get('CELERY_LOG_LEVEL')))


def pytb_lastline(excinfo=None):
    """Return the actual last line of the (current) traceback.

    To provide exc_info, rather than allowing this function
    to read the stack automatically, this function may be called like so:
        ll = pytb_lastline(sys.exc_info())
    OR
        try:
            1/0
        except Exception as err:
            ll = pytb_lastline(err)
    """
    # TODO(samstav): Add this to airbrake-python utils
    lines = None
    if excinfo:
        if isinstance(excinfo, Exception):
            kls = getattr(excinfo, '__class__', '')
            if kls:
                kls = str(getattr(kls, '__name__', ''))
                kls = ("%s: " % kls) if kls else ''
            lines = [kls + str(excinfo)]
        else:
            try:
                lines = traceback_module.format_exception(*excinfo)
                lines = "\n".join(lines).split('\n')
            except (TypeError, AttributeError) as err:
                LOG.error("Bad argument %s passed to pytb_lastline()."
                          "Should be sys.exc_info() or None.", excinfo,
                          exc_info=err)
    if not lines:
        lines = traceback_module.format_exc().split('\n')
    # remove Falsy values and the word "None"
    lines = [line.strip() for line in lines
             if line.strip() and line.strip() != 'None']
    if lines:
        return lines[-1]


def scrub_data(data, conf=None, exempt=None):
    """Remove password and conf values from dict.

    :param data:    A dict or iterable of results to sanitize.
    :param config:  A dict (optional) of config values to sanitize
                    against in addition to the common keys.
    :param exempt:  An iterable of strings which qualify as exempt from
                    sanitization. Matches must be exact. Be careful.
    Santitize results and remove potentially sensitive data.
    Iterates through results and removes any values that match
    keys found in either `config` or `blacklist`. Returns
    sanitized results dict.
    """
    secrets = {'password', 'passphrase', 'token', 'key', 'user', 'secret'}
    if exempt and not isinstance(exempt, list):
        raise TypeError("'exempt' should be a list of exempted keys.")
    exempt = exempt or []

    if isinstance(data, dict):
        result = copy.deepcopy(data)
        for key, value in result.items():
            if not value:
                continue
            if key in exempt:
                LOG.warning("Key '%s' has been exempted from sanitization "
                            "on this call.", key)
                result[key] = scrub_data(value)
            if conf:
                if key in conf:
                    LOG.debug("Sanitized %s from dict.", key)
                    result[key] = '*****'
                    continue
            elif any(w in str(key).lower() for w in secrets):
                LOG.debug("Sanitized %s from dict.", key)
                result[key] = '*****'
            elif 'key' in str(key).lower():
                if value.startswith('-----'):
                    result[key] = '%s...%s' % (value[0:25], value[-25:])
                else:
                    result[key] = '*****'
                LOG.debug("Sanitized %s from dict.", key)
            elif any((w in str(key).lower() for w in
                      {'url', 'connection', 'backend', 'broker'})):
                result[key] = hide_url_password(value)
            else:
                result[key] = scrub_data(value)
        return result
    elif isinstance(data, tuple):
        return tuple(scrub_data(x) for x in data)
    elif isinstance(data, set):
        return {scrub_data(x) for x in data}
    elif isinstance(data, list):
        return [scrub_data(x) for x in data]
    else:
        return data


def import_class(import_str):
    """Return a class from a string including module and class."""
    mod_str, _, class_str = import_str.rpartition('.')
    try:
        __import__(mod_str)
        return getattr(sys.modules[mod_str], class_str)
    except (ImportError, ValueError, AttributeError) as exc:
        LOG.debug('Inner Exception: %s', exc)
        raise


def import_object(import_str, *args, **kw):
    """Return an object including a module or module and class."""
    try:
        __import__(import_str)
        return sys.modules[import_str]
    except ImportError:
        cls = import_class(import_str)
        return cls(*args, **kw)


def resolve_yaml_external_refs(document):
    """Parse YAML and resolves any external references.

    :param document: a stream object
    :returns: an iterable
    """
    anchors = []
    for event in yaml.parse(document, Loader=yaml.SafeLoader):
        if isinstance(event, events.AliasEvent):
            if event.anchor not in anchors:
                # Swap out local reference for external reference
                new_ref = u'ref://%s' % event.anchor
                event = events.ScalarEvent(anchor=None, tag=None,
                                           implicit=(True, False),
                                           value=new_ref)
        if hasattr(event, 'anchor') and event.anchor:
            anchors.append(event.anchor)

        yield event


def read_body(request):
    """Read request body considering content-type and returns it as a dict."""
    data = request.body
    if not data or getattr(data, 'len', -1) == 0:
        raise cmexc.CheckmateNoData("No data provided")
    content_type = request.get_header(
        'Content-type', 'application/json')
    if ';' in content_type:
        content_type = content_type.split(';')[0]

    if content_type == 'application/x-yaml':
        try:
            return yaml_to_dict(data)
        except (parser.ParserError, scanner.ScannerError) as exc:
            raise cmexc.CheckmateValidationException(
                friendly_message="Invalid YAML syntax. Check:\n%s" % exc,
                http_status=406)
        except composer.ComposerError as exc:
            raise cmexc.CheckmateValidationException(
                friendly_message="Invalid YAML structure. Check:\n%s" % exc,
                http_status=406)

    elif content_type == 'application/json':
        try:
            return json.load(data)
        except ValueError as exc:
            raise cmexc.CheckmateValidationException(
                friendly_message="Invalid JSON. %s" % exc,
                http_status=406)
    elif content_type == 'application/x-www-form-urlencoded':
        obj = request.forms.object
        if obj:
            result = json.loads(obj)
            if result:
                return result
        raise cmexc.CheckmateValidationException(
            friendly_message=("Unable to parse content. Form POSTs only "
                              "support objects in the 'object' field"),
            http_status=406)
    else:
        raise cmexc.CheckmateException(
            friendly_message="Unsupported Media Type: %s" % content_type,
            http_status=415)


def yaml_to_dict(data):
    """Parse YAML to a dict using checkmate extensions."""
    return yaml.safe_load(yaml.emit(resolve_yaml_external_refs(data),
                                    Dumper=yaml.SafeDumper))


def dict_to_yaml(data):
    """Parse dict to YAML using checkmate extensions."""
    return yaml.safe_dump(data, default_flow_style=False)


def write_yaml(data, request, response):
    """Write output in yaml."""
    response.set_header('content-type', 'application/x-yaml')
    return to_yaml(data)


def to_yaml(data):
    """Write python object to YAML.

    Includes special handling for Checkmate objects derived from MutableMapping
    """
    if isinstance(data, collections.MutableMapping) and hasattr(data, '_data'):
        return yaml.safe_dump(data._data, default_flow_style=False)
    return yaml.safe_dump(data, default_flow_style=False)


def escape_yaml_simple_string(text):
    """Render a simple string as valid YAML string escaping where necessary.

    Note: Skips formatting if value supplied is not a string or is a multi-line
          string and just returns the value unmodified
    """
    # yaml seems to append \n or \n...\n in certain circumstances
    if text is None or (isinstance(text, basestring) and '\n' not in text):
        return yaml.safe_dump(text).strip('\n').strip('...').strip('\n')
    else:
        return text


def write_json(data, request, response):
    """Write output in json."""
    response.set_header('Content-Type', 'application/json')
    return to_json(data)


def to_json(data):
    """Write out python object to JSON.

    Includes special handling for Checkmate objects derived from MutableMapping
    """
    if isinstance(data, collections.MutableMapping) and hasattr(data, 'dumps'):
        return data.dumps(indent=4)
    return json.dumps(data, indent=4)


def try_int(the_str):
    """Try converting string to int. Return the string on failure."""
    try:
        return int(the_str)
    except ValueError:
        return the_str

HANDLERS = {
    'application/x-yaml': write_yaml,
    'application/json': write_json,
    'default': write_json
}


def formatted_response(uripath, with_pagination=False):
    """A function decorator for http responses.

    A function decorator that adds pagination information to the response
    header of a route/get/post/put function.
    """
    def _formatted_response(fxn):
        """Add pagination (optional) and headers to response."""
        def _decorator(*args, **kwargs):
            """Internal function wrapped as a decorator."""
            try:
                _validate_range_values(bottle.request, 'offset', kwargs)
                _validate_range_values(bottle.request, 'limit', kwargs)
            except ValueError:
                bottle.response.status = 416
                bottle.response.set_header('Content-Range', '%s */*' % uripath)
                return

            data = fxn(*args, **kwargs)
            context = bottle.request.environ['context']
            tenant_id = kwargs.get('tenant_id', context.tenant)
            if with_pagination:
                _write_pagination_headers(
                    data,
                    kwargs.get('offset') or 0,
                    kwargs.get('limit') or 100,
                    bottle.response,
                    uripath,
                    tenant_id
                )
            if 'deployments' in uripath:
                expected_tenant = kwargs.get(
                    'tenant_id', bottle.request.environ['context'].tenant)
                if context.is_admin is True:
                    LOG.info('An Administrator performed a GET on deployments '
                             'with Tenant ID %s.', expected_tenant)
                elif expected_tenant:
                    for _, deployment in data['results'].items():
                        if (deployment.get('tenantId') and
                                deployment['tenantId'] != expected_tenant):
                            LOG.warn(
                                'Cross-Tenant Violation in '
                                'formatted_response: requested tenant %s does '
                                'not match tenant %s in response.\nLocals:\n '
                                '%s\nGlobals:\n%s', expected_tenant,
                                deployment['tenandId'], locals(), globals()
                            )
                            raise cmexc.CheckmateDataIntegrityError(
                                'A Tenant ID in the results '
                                'does not match %s.',
                                expected_tenant
                            )
            return write_body(
                data,
                bottle.request,
                bottle.response
            )
        return functools.wraps(fxn)(_decorator)
    return _formatted_response


def _validate_range_values(request, label, kwargs):
    """Ensure value contained in label is a positive integer."""
    value = kwargs.get(label, request.query.get(label))
    if value:
        kwargs[label] = int(value)
        if kwargs[label] < 0 or kwargs[label] > 10000000:
            raise ValueError


def _write_pagination_headers(data, offset, limit, response,
                              uripath, tenant_id=None):
    """Add pagination headers to the response body."""
    count = len(data.get('results'))
    if 'collection-count' in data:
        total = int(data.get('collection-count', 0))
    elif offset == 0 and (limit is None or limit > data['results'].count()):
        total = count
    else:
        total = None
    url = uripath
    if tenant_id:
        url = '%s/%s' % (tenant_id, uripath)
    # Set 'content-range' header
    response.set_header(
        'Content-Range',
        "%s %d-%d/%s" % (uripath, offset, offset + max(count - 1, 0),
                         total if total is not None else '*')
    )

    if offset != 0 or total > count:
        response.status = 206  # Partial

        # Add Next page link to http header
        if (offset + limit) < total - 1:
            nextfmt = ('</%s?limit=%d&offset=%d>; '
                       'rel="next"; title="Next page"')
            response.add_header(
                "Link", nextfmt % (url, limit, offset + limit)
            )

        # Add Previous page link to http header
        if offset > 0 and (offset - limit) >= 0:
            prevfmt = ('</%s?limit=%d&offset=%d>; rel="previous"; '
                       'title="Previous page"')
            response.add_header(
                "Link", prevfmt % (url, limit, offset - limit)
            )

        # Add first page link to http header
        if offset > 0:
            firstfmt = '</%s?limit=%d>; rel="first"; title="First page"'
            response.add_header(
                "Link", firstfmt % (url, limit))

        # Add last page link to http header
        if limit and limit < total:
            lastfmt = '</%s?offset=%d>; rel="last"; title="Last page"'
            if limit and total % limit:
                last_offset = total - (total % limit)
            else:
                last_offset = total - limit
            response.add_header(
                "Link", lastfmt % (url, last_offset))


def write_body(data, request, response):
    """Write output with format based on accept header.

    This cycles through the global HANDLERs to match content type and then
    calls that handler. Additional handlers can be added to support Additional
    content types.
    """
    response.set_header('vary', 'Accept,Accept-Encoding,X-Auth-Token')
    accept = request.get_header('Accept', ['application/json'])

    for content_type in HANDLERS:
        if content_type in accept:
            return HANDLERS[content_type](
                data, request, response)

    # Use default
    return HANDLERS['default'](data, request, response)


def extract_sensitive_data(data, sensitive_keys=None):
    """Parse the dict passed in, extracting all sensitive data.

    Extracted data is placed into another dict, and returns two dicts; one
    without the sensitive data and with only the sensitive data.

    :param sensitive_keys: a list of keys considered sensitive
    """
    def key_match(key, sensitive_keys):
        """Determine whether or not key is in sensitive_keys."""
        if key in sensitive_keys:
            return True
        if key is None:
            return False
        for reg_expr in [pattern for pattern in sensitive_keys
                         if hasattr(pattern, "search")
                         and callable(getattr(pattern, "search"))]:
            if reg_expr.search(key):
                return True
        return False

    def recursive_split(data, sensitive_keys=None):
        """Return split dict or list if it contains any sensitive fields."""
        if sensitive_keys is None:  # Safer than default value
            sensitive_keys = []
        clean = None
        sensitive = None
        has_sensitive_data = False
        has_clean_data = False
        if isinstance(data, list):
            clean = []
            sensitive = []
            for value in data:
                if isinstance(value, dict):
                    clean_value, sensitive_value = recursive_split(
                        value, sensitive_keys=sensitive_keys)
                    if sensitive_value is not None:
                        sensitive.append(sensitive_value)
                        has_sensitive_data = True
                    else:
                        sensitive.append({})  # placeholder
                    if clean_value is not None:
                        clean.append(clean_value)
                        has_clean_data = True
                    else:
                        clean.append({})  # placeholder
                elif isinstance(value, list):
                    clean_value, sensitive_value = recursive_split(
                        value, sensitive_keys=sensitive_keys)
                    if sensitive_value is not None:
                        sensitive.append(sensitive_value)
                        has_sensitive_data = True
                    else:
                        sensitive.append([])  # placeholder
                    if clean_value is not None:
                        clean.append(clean_value)
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
                if key_match(key, sensitive_keys):
                    has_sensitive_data = True
                    sensitive[key] = value
                elif isinstance(value, dict):
                    clean_value, sensitive_value = recursive_split(
                        value, sensitive_keys=sensitive_keys)
                    if sensitive_value is not None:
                        has_sensitive_data = True
                        sensitive[key] = sensitive_value
                    if clean_value is not None:
                        has_clean_data = True
                        clean[key] = clean_value
                elif isinstance(value, list):
                    clean_value, sensitive_value = recursive_split(
                        value, sensitive_keys=sensitive_keys)
                    if sensitive_value is not None:
                        has_sensitive_data = True
                        sensitive[key] = sensitive_value
                    if clean_value is not None:
                        has_clean_data = True
                        clean[key] = clean_value
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


def flatten(list_of_dict):
    """Convert a list of dictionary to a single dictionary.

    If 2 or more dictionaries have the same key then the data from the last
    dictionary in the list will be taken.
    """
    result = {}
    for entry in list_of_dict:
        result.update(entry)
    return result


def merge_dictionary(dst, src, extend_lists=False):
    """Recursively merge two dicts.

    Hashes at the root level are NOT overwritten

    Note: This updates dst.
    """
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
                    merge_lists(dest, source, extend_lists=extend_lists)
                else:
                    current_dst[key] = source
    return dst


def merge_lists(dest, source, extend_lists=False):
    """Recursively merge two lists.

    This applies merge_dictionary if any of the entries are dicts.
    Note: This updates dst.
    """
    if not source:
        return
    if not extend_lists:
        # Make them the same size
        left = dest
        right = source[:]
        if len(dest) > len(source):
            right.extend([None for _ in range(len(dest) - len(source))])
        elif len(dest) < len(source):
            left.extend([None for _ in range(len(source) - len(dest))])
        # Merge lists
        for index, value in enumerate(left):
            if value is None and right[index] is not None:
                dest[index] = right[index]
            elif isinstance(value, dict) and \
                    isinstance(right[index], dict):
                merge_dictionary(dest[index], source[index],
                                 extend_lists=extend_lists)
            elif isinstance(value, list):
                merge_lists(value, right[index])
            elif right[index] is not None:
                dest[index] = right[index]
    else:
        dest.extend([src for src in source if src not in dest])
    return dest


def is_ssh_key(key):
    """Check if string looks like it is an ssh key."""
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
    key_string = parts[1]
    try:
        data = base64.decodestring(key_string)
    except StandardError:
        return False
    int_len = 4
    str_len = struct.unpack('>I', data[:int_len])[0]  # this should return 7
    if str_len != 7:
        return False
    if data[int_len:int_len + str_len] == 'ssh-rsa':
        return True
    return False


def get_class_name(instance):
    """Return instance's class name."""
    return instance.__class__.__name__


def get_source_body(function):
    """Get the body of a function (i.e. no definition line, and unindented."""
    lines = inspect.getsource(function).split('\n')

    # Find body - skip decorators and definition
    start = 0
    for number, line in enumerate(lines):
        if line.strip().startswith("@"):
            start = number + 1
        elif line.strip().startswith("def "):
            start = number + 1
            break
    lines = lines[start:]

    # Unindent body
    indent = len(lines[0]) - len(lines[0].lstrip())
    for index, line in enumerate(lines):
        lines[index] = line[indent:]
    return '\n'.join(lines)


def with_tenant(fxn):
    """Ensure a context tenant_id is passed into decorated function.

    A function decorator that ensures a context tenant_id is passed in to
    the decorated function as a kwarg
    """
    def wrapped(*args, **kwargs):
        """Internal function wrapped as a decorator."""
        if kwargs.get('tenant_id'):
            # Tenant ID is being passed in
            return fxn(*args, **kwargs)
        else:
            return fxn(*args,
                       tenant_id=bottle.request.environ['context'].tenant,
                       **kwargs)
    return functools.wraps(fxn)(wrapped)


def support_only(types):
    """Ensure route is only accepted if content type is supported.

    A function decorator that ensures the route is only accepted if the
    content type is in the list of types supplied
    """
    def wrap(fxn):
        """Internal function wrapped as a decorator."""
        def wrapped(*args, **kwargs):
            """Internal function wrapped as a decorator."""
            accept = bottle.request.get_header("Accept", [])
            if accept == "*/*":
                return fxn(*args, **kwargs)
            for content_type in types:
                if content_type in accept:
                    return fxn(*args, **kwargs)
            LOG.debug("support_only decorator filtered call")
            raise bottle.abort(415, "Unsupported media type")
        return wrapped
    return wrap


def only_admins(fxn):
    """Decorator to limit access to admins only."""
    def wrapped(*args, **kwargs):
        """Internal function wrapped as a decorator."""
        if bottle.request.environ['context'].is_admin is True:
            LOG.debug("Admin account '%s' accessing '%s'",
                      bottle.request.environ['context'].username,
                      bottle.request.path)
            return fxn(*args, **kwargs)
        else:
            bottle.abort(
                403, "Administrator privileges needed for this operation")
    return wrapped


def get_time_string(time_gmt=None):
    """The Checkmate canonical time string format.

    Changing this function will change all times that checkmate uses in
    blueprints, deployments, etc...
    """
    # TODO(Pablo): We should assert that time_gmt is a time.struct_time
    return time.strftime("%Y-%m-%d %H:%M:%S +0000", time_gmt or time.gmtime())


def is_uuid(value):
    """Test that a provided value is a valid uuid."""
    if not value:
        return False
    if isinstance(value, uuid.UUID):
        return True
    try:
        uuid.UUID(value)
        return True
    except StandardError:
        return False


def write_path(target, path, value):
    """Write a value into a dict building any intermediate keys."""
    parts = path.split('/')
    current = target
    for part in parts[:-1]:
        if part not in current:
            current[part] = current = {}
        else:
            current = current[part]
    current[parts[-1]] = value


def read_path(source, path):
    """Read a value from a dict supporting a path as a key."""
    parts = path.strip('/').split('/')
    current = source
    for part in parts[:-1]:
        if part not in current:
            return
        current = current[part]
        if not isinstance(current, collections.MutableMapping):
            return
    return current.get(parts[-1])


def path_exists(source, path):
    """Check a dict for the existence of a path as a key."""
    if path == '/' and isinstance(source, dict):
        return True
    parts = path.strip('/').split('/')
    if not parts:
        return False
    current = source
    for part in parts:
        if not isinstance(current, collections.MutableMapping):
            return False
        if part not in current:
            return False
        current = current[part]
    return True


def is_evaluable(value):
    """Check if value is a function that can be passed to evaluate()."""
    try:
        return (value.startswith('=generate_password(') or
                value.startswith('=generate_uuid('))
    except AttributeError:
        return False


def generate_password(min_length=None, max_length=None, required_chars=None,
                      starts_with=string.ascii_letters, valid_chars=None):
    """Generate a password based on constraints provided.

    :param min_length: minimum password length
    :param max_length: maximum password length
    :param required_chars: a set of character sets, one for each required char
    :param starts_with: a set of characters required as the first character
    :param valid_chars: the set of valid characters for non-required chars
    """
    # Raise Exception if max_length exceeded
    if min_length > 255 or max_length > 255:
        raise ValueError('Maximum password length of 255 characters exceeded.')

    # Choose a valid password length based on min_length and max_length
    if max_length and min_length and max_length != min_length:
        password_length = random.randint(min_length, max_length)
    else:
        password_length = max_length or min_length or 12

    # If not specified, default valid_chars to letters and numbers
    valid_chars = valid_chars or ''.join([
        string.ascii_letters,
        string.digits
    ])

    first_char = ''
    if starts_with:
        first_char = random.choice(starts_with)
        password_length -= 1

    password = ''
    if required_chars:
        for required_set in required_chars:
            if password_length > 0:
                password = ''.join([password, random.choice(required_set)])
                password_length -= 1
            else:
                raise ValueError(
                    'Password length is less than the '
                    'number of required characters.'
                )

    if password_length > 0:
        password = ''.join([
            password,
            ''.join(
                [random.choice(valid_chars) for _ in range(password_length)]
            )
        ])

    # Shuffle all except first_char
    password = ''.join(random.sample(password, len(password)))

    return '%s%s' % (first_char, password)


def evaluate(function_string):
    """Evaluate an option value.

    Understands the following functions:
    - generate_password()
    - generate_uuid()
    """
    func_name, kwargs = codegen.kwargs_from_string(function_string)
    if func_name == 'generate_uuid':
        return uuid.uuid4().hex
    if func_name == 'generate_password':
        return generate_password(**kwargs)
    raise NameError("Unsupported function: %s" % function_string)


def execute_shell(command, with_returncode=True, cwd=None, strip=True):
    """Execute a command (containing no shell operators) locally.

    Raises CheckmateCalledProcessError on non-zero exit status.

    :param command:         Shell command to be executed. If the value is
                            a string, it will be split using shlex.split()
                            to return a shell-like syntax as a list. If the
                            value is a list, it will be passed directly to
                            Popen.
    :param with_returncode: Include the exit_code in the return body.
                            Default is True.
    :param cwd:             The child's current directory will be changed
                            to `cwd` before it is executed. Note that this
                            directory is not considered when searching the
                            executable, so you can't specify the program's
                            path relative to this argument. Value should not
                            be quoted or shell escaped, since it is passed
                            directly to os.chdir() by subprocess.Popen
    :param strip:           Strip the output of whitespace using str.strip()
    :returns:               A dict with 'stdout', and (optionally),
                            'returncode'

    Note:   Popen is called with stderr=subprocess.STDOUT, which sends
            all stderr to stdout.
    """
    if isinstance(command, basestring):
        cmd = shlex.split(command)
    elif isinstance(command, list):
        cmd = command
        command = " ".join(cmd)
    else:
        raise TypeError("'command' should be a string or a list")
    LOG.debug("Executing `%s` on local machine", command)
    LOG.debug("Command after split: %s", cmd)
    try:
        pope = subprc.Popen(
            cmd, stdout=subprc.PIPE, stderr=subprc.STDOUT, cwd=cwd,
            universal_newlines=True)
    except OSError as err:
        raise cmexc.CheckmateCalledProcessError(
            1, command, output=repr(err))
    out, err = pope.communicate()
    assert not err
    out = {'stdout': out.strip() if strip else out}
    if pope.returncode != 0:
        raise cmexc.CheckmateCalledProcessError(
            pope.returncode, command, output=out['stdout'])
    if with_returncode:
        out.update({'returncode': pope.returncode})
    return out


def check_all_output(params, find="ERROR", env=None, cwd=None):
    """Detect 'find' string in params, returning a list of all matching lines.

    Similar to subprocess.check_output, but parses both stdout and stderr
    and detects any string passed in as the find parameter.

    :returns: tuple (stdout, stderr, lines with :param:find in them)

    We used this for processing Knife output where the details of the error
    were piped to stdout and the actual error did not have everything we
    needed because knife did not exit with an error code, but now we're just
    keeping it for the script provider (coming soon)
    """
    on_posix = 'posix' in sys.builtin_module_names

    def start_thread(func, *args):
        """Start thread as a daemon."""
        thread = threading.Thread(target=func, args=args)
        thread.daemon = True
        thread.start()
        return thread

    def consume(infile, output, found):
        """Per thread: read lines in file searching for find."""
        for line in iter(infile.readline, ''):
            output(line)
            if find in line:
                found(line)
        infile.close()

    process = subprc.Popen(params, stdout=subprc.PIPE,
                           stderr=subprc.PIPE, bufsize=1,
                           close_fds=on_posix, env=env, cwd=cwd)

    # preserve last numlines of stdout and stderr
    numlines = 100
    stdout = collections.deque(maxlen=numlines)
    stderr = collections.deque(maxlen=numlines)
    found = collections.deque(maxlen=numlines)
    threads = [start_thread(consume, *args)
               for args in (process.stdout, stdout.append, found.append),
               (process.stderr, stderr.append, found.append)]
    for thread in threads:
        thread.join()  # wait for IO completion

    retcode = process.wait()

    if retcode == 0:
        return (stdout, stderr, found)
    else:
        msg = "stdout: %s \n stderr: %s \n Found: %s" % (stdout, stderr, found)
        LOG.debug(msg)
        raise cmexc.CheckmateCalledProcessError(
            retcode, ' '.join(params),
            output='\n'.join(stdout),
            error_info='%s%s' % ('\n'.join(stderr), '\n'.join(found)))


def is_simulation(api_id):
    """Determine if the current object is in simulation."""
    return str(api_id).startswith('simulate')


def get_id(is_sim):
    """Generate id: prepend 'simulate' for simulations."""
    if is_sim:
        return 'simulate%s' % uuid.uuid4().hex[0:12]
    else:
        return uuid.uuid4().hex


def copy_contents(source, dest, with_overwrite=False, create_path=True):
    """Copy the contents of a `source' directory to `dest'.

    It's affect is roughly equivalent to the following shell command:

    mkdir -p /path/to/dest && cp -r /path/to/source/* /path/to/dest/

    """
    if not os.path.exists(dest):
        if create_path:
            os.makedirs(dest)
        else:
            raise IOError("%s does not exist.  Use create_path=True to create "
                          "destination" % dest)
    for src_file in os.listdir(source):
        source_path = os.path.join(source, src_file)
        if os.path.isdir(source_path):
            try:
                shutil.copytree(source_path, os.path.join(dest, src_file))
            except OSError as exc:
                if exc.errno == 17:  # File exists
                    if with_overwrite:
                        shutil.rmtree(os.path.join(dest, src_file))
                        shutil.copytree(
                            source_path, os.path.join(dest, src_file))
                    else:
                        raise IOError("%s exists, use with_overwrite=True to "
                                      "overwrite destination." % dest)
        else:
            shutil.copy(source_path, dest)


def filter_resources(resources, provider_name):
    """Return resources of a specified type."""
    results = []
    for resource in resources.values():
        if 'provider' in resource:
            if resource['provider'] == provider_name:
                results.append(resource)
    return results


def cap_limit(limit, tenant_id):
    """Check limit param and resets it to max allowable if needed."""
    # So that we don't end up with a DoS due to unchecked limit:
    if limit is None or limit > 100 or limit < 0:
        LOG.warn('Request for tenant %s with limit of %s. Defaulting '
                 'limit to 100.', tenant_id, limit)
        return 100
    return limit


def get_ips_from_server(server, is_rackconnected_account=False,
                        primary_address_type='public'):
    """Extract ip addresses from a server object."""
    ip_addr = None
    result = {}
    addresses = server.addresses.get(primary_address_type, [])
    for address in addresses:
        if address['version'] == 4:
            ip_addr = address['addr']
            break
    if ((primary_address_type != 'public' and server.accessIPv4) or
            is_rackconnected_account):
        ip_addr = server.accessIPv4
        LOG.info("Using accessIPv4 to connect: %s", ip_addr)
    result['ip'] = ip_addr

    public_addresses = server.addresses.get('public', [])
    for address in public_addresses:
        if address['version'] == 4:
            result['public_ip'] = address['addr']
            break

    private_addresses = server.addresses.get('private', [])
    for address in private_addresses:
        if address['version'] == 4:
            result['private_ip'] = address['addr']
            break

    return result


def is_rackconnect_account(context):
    """Check if the context for RackConnect account.

    Check if the context has information that indicates that the account
    is a RackConnect account
    """
    return 'rack_connect' in context['roles']


class Simulation(object):

    """Generic object used to set simulation attrs."""

    def __init__(self, *args, **kwargs):
        """Assign arguments to attributes, 'kwargs' sets key to attr name."""
        self.args = args
        for key, value in kwargs.items():
            setattr(self, key, value)


class QueryParams(object):

    """Query Parameters Class."""

    @staticmethod
    def parse(params, whitelist=None):
        """Parse query params based on whitelist if provided."""
        keys = params.keys()
        if whitelist:
            keys = whitelist

        query = {}
        query['whitelist'] = keys

        for key in keys:
            if key in params:
                value = params[key]
                if value and len(value) == 1:
                    value = value[0]

                if value:
                    query[key] = value

        return query


def hide_url_password(url):
    """Detect a password part of a URL and replaces it with *****."""
    try:
        parsed = urlparse.urlsplit(url)
        if parsed.password:
            return url.replace(':%s@' % parsed.password, ':*****@')
    except StandardError:
        pass
    return url


def set_url_creds(url, username=None, password=None):
    """Return url with credentials set as supplied."""
    parsed = urlparse.urlsplit(url)
    scheme, netloc, path, query, fragment = parsed
    netloc = "%s:%s@%s:%s" % (username or '', password or '',
                              parsed.hostname, parsed.port or '')
    netloc = netloc.replace(":@", "@").strip(':@')
    result = urlparse.SplitResult(scheme=scheme, netloc=netloc, path=path,
                                  query=query, fragment=fragment)
    return urlparse.urlunsplit(result)


def format_check(data):
    """Calculate a deployment's deltas and returns a formatted result.

    :param data: a dict containing 4 sections (see expected_keys)
    """
    data = data or {}
    body = {'resources': {}}
    instance = {}
    desired = {}

    # Extract the data
    for key, value in data.iteritems():
        if all(section in value for section in ('desired-state', 'instance')):
            instance[key] = value['instance']
            instance[key]['region'] = value.get('region')
            desired[key] = value['desired-state']
        elif 'desired-state' in value:  # instance is missing
            body['resources'][key] = [
                {
                    'type': 'WARNING',
                    'message': ('Resource %s has desired-state '
                                'but no instance.' % key)
                }
            ]

    # Build the output
    for resource, checks in desired.iteritems():
        body['resources'][resource] = []
        for setting, value in checks.iteritems():
            if instance[resource].get(setting) is None:
                body['resources'][resource].append({
                    'type': 'WARNING',
                    'message': '%s does not exist in instance.' % setting
                })
            elif value == instance[resource].get(setting):
                body['resources'][resource].append({
                    'type': 'INFORMATION',
                    'message': '%s %s is valid.' % (setting, value)
                })
            else:
                body['resources'][resource].append(
                    {
                        'type': 'WARNING',
                        'message': ("%s invalid: currently '%s'. "
                                    "Should be '%s'."
                                    % (setting,
                                       instance[resource].get(setting),
                                       value))
                    }
                )
    return body


def run_ruby_command(path, command, params, env=None, lock=True):
    """Run a knife-like command (ex. librarian-chef).

    Since knife-like command errors are returned to stderr, we need to
    capture stderr and check for errors.

    That needs to be run in a kitchen, so we move curdir and need to make
    sure we stay there, so I added some synchronization code while that
    takes place. However, if code calls in that already has a lock,
    the optional lock param can be set to false so this code does not
    lock.
    """
    params.insert(0, command)
    LOG.debug("Running: '%s' in path '%s'", ' '.join(params), path)
    if lock:
        path_lock = threading.Lock()
        path_lock.acquire()
        try:
            if path:
                os.chdir(path)
            result = subprc.check_output(params, cwd=path, env=env)
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                # Check if command is installed
                output = None
                try:
                    output = subprc.check_output(['which', command])
                except subprc.CalledProcessError:
                    pass
                if not output:
                    msg = ("'%s' is not installed or not accessible on "
                           "the server" % command)
                    raise cmexc.CheckmateException(msg)
            raise exc
        except subprc.CalledProcessError as exc:
            # retry and pass ex
            # CalledProcessError cannot be serialized using Pickle,
            # so raising it would fail in celery; we wrap the exception in
            # something Pickle-able.
            msg = exc.output
            raise cmexc.CheckmateCalledProcessError(exc.returncode, exc.cmd,
                                                    output=msg)
        finally:
            path_lock.release()
    else:
        if path:
            os.chdir(path)
        result = subprc.check_output(params, cwd=path, env=env)
    LOG.debug(result)
    return result


class MutatingIterator(object):  # pylint: disable=R0903

    """This class iterates over a changing dict.

    Example usage:

        data = {1: 1}

        for var in MutatingIterator(data):
            print var
            if var < 4:
                data[var+1] = ''
        > 1
        > 2
        > 3
        > 3
    """

    def __init__(self, data):
        """Initialize the iterator with data."""
        self.data = data

    class Iterator(object):  # pylint: disable=R0903

        """Iterator over changing dict."""

        def __init__(self, data):
            self.data = data
            self.visited = set()

        def __next__(self):
            """Python 3 compatible call."""
            return self.next()

        def next(self):
            """Next instantated manager."""
            for key in self.data.iterkeys():
                if key not in self.visited:
                    self.visited.add(key)
                    return key
            raise StopIteration()

    def __iter__(self):
        """Run the iterator."""
        return MutatingIterator.Iterator(self.data)
