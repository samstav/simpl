# Copyright (c) 2011-2013 Rackspace Hosting
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

""" General utility functions

- handling content conversion (yaml/json)
- handling templating (Jinja2)
"""
import base64
import collections
import inspect
import json
import logging.config
import os
import re
import shutil
import string
import struct
import subprocess as subprc
import sys
import time
import urlparse
import uuid

import bottle
from Crypto.Random import random
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


def get_debug_level(config):
    """Get debug settings from arguments.

    --debug: turn on additional debug code/inspection (implies logging.DEBUG)
    --verbose: turn up logging output (logging.DEBUG)
    --quiet: turn down logging output (logging.WARNING)
    default is logging.INFO
    """
    if config.debug is True:
        return logging.DEBUG
    elif config.verbose is True:
        return logging.DEBUG
    elif config.quiet is True:
        return logging.WARNING
    else:
        return logging.INFO


class DebugFormatter(logging.Formatter):
    """Log formatter.

    Outputs any 'data' values passed in the 'extra' parameter if provided.
    """
    def format(self, record):
        # Print out any 'extra' data provided in logs
        if hasattr(record, 'data'):
            return "%s. DEBUG DATA=%s" % (logging.Formatter.format(self,
                                          record), record.__dict__['data'])
        return logging.Formatter.format(self, record)


def get_debug_formatter(config):
    """Get debug formatter based on configuration.

    :param config: configurtration namespace (ex. argparser)

    --debug: log line numbers and file data also
    --verbose: standard debug
    --quiet: turn down logging output (logging.WARNING)
    default is logging.INFO
    """
    if config.debug is True:
        return DebugFormatter('%(pathname)s:%(lineno)d: %(levelname)-8s '
                              '%(message)s')
    elif config.verbose is True:
        return logging.Formatter('%(name)-30s: %(levelname)-8s %(message)s')
    elif config.quiet is True:
        return logging.Formatter('%(message)s')
    else:
        return logging.Formatter('%(message)s')


def find_console_handler(logger):
    """Returns a stream handler, if it exists."""
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler) and \
                handler.stream == sys.stderr:
            return handler


def init_logging(config, default_config=None):
    """Configure logging

    :param config: object with configuration namespace (argparse parser)
    """
    if config.logconfig:
        logging.config.fileConfig(config.logconfig,
                                  disable_existing_loggers=False)
    elif default_config and os.path.isfile(default_config):
        logging.config.fileConfig(default_config,
                                  disable_existing_loggers=False)
    else:
        init_console_logging(config)


def init_console_logging(config):
    """Log to console."""
    # define a Handler which writes messages to the sys.stderr
    console = find_console_handler(logging.getLogger())
    if not console:
        logging_level = get_debug_level(config)
        console = logging.StreamHandler()
        console.setLevel(logging_level)

        # set a format which is simpler for console use
        formatter = get_debug_formatter(config)
        # tell the handler to use this format
        console.setFormatter(formatter)
        # add the handler to the root logger
        logging.getLogger().addHandler(console)
        logging.getLogger().setLevel(logging_level)
        global LOG
        LOG = logging.getLogger(__name__)  # reset


def match_celery_logging(logger):
    """Match celery log level."""
    if logger.level < int(os.environ.get('CELERY_LOG_LEVEL', logger.level)):
        logger.setLevel(int(os.environ.get('CELERY_LOG_LEVEL')))


def import_class(import_str):
    """Returns a class from a string including module and class."""
    mod_str, _, class_str = import_str.rpartition('.')
    try:
        __import__(mod_str)
        return getattr(sys.modules[mod_str], class_str)
    except (ImportError, ValueError, AttributeError) as exc:
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
    """Reads request body considering content-type and returns it as a dict."""
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
            raise cmexc.CheckmateValidationException("Invalid YAML syntax. "
                                                     "Check:\n%s" % exc)
        except composer.ComposerError as exc:
            raise cmexc.CheckmateValidationException("Invalid YAML structure. "
                                                     "Check:\n%s" % exc)

    elif content_type == 'application/json':
        return json.load(data)
    elif content_type == 'application/x-www-form-urlencoded':
        obj = request.forms.object
        if obj:
            result = json.loads(obj)
            if result:
                return result
        raise cmexc.CheckmateValidationException("Unable to parse content. "
                                                 "Form POSTs only support "
                                                 "objects in the 'object' "
                                                 "field")
    else:
        bottle.abort(415, "Unsupported Media Type: %s" % content_type)


def yaml_to_dict(data):
    """Parses YAML to a dict using checkmate extensions."""
    return yaml.safe_load(yaml.emit(resolve_yaml_external_refs(data),
                                    Dumper=yaml.SafeDumper))


def dict_to_yaml(data):
    """Parses dict to YAML using checkmate extensions."""
    return yaml.safe_dump(data, default_flow_style=False)


def write_yaml(data, request, response):
    """Write output in yaml."""
    response.set_header('content-type', 'application/x-yaml')
    return to_yaml(data)


def to_yaml(data):
    """Writes python object to YAML.

    Includes special handling for Checkmate objects derived from MutableMapping
    """
    if isinstance(data, collections.MutableMapping) and hasattr(data, '_data'):
        return yaml.safe_dump(data._data, default_flow_style=False)
    return yaml.safe_dump(data, default_flow_style=False)


def escape_yaml_simple_string(text):
    """Renders a simple string as valid YAML string escaping where necessary.

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
    response.set_header('content-type', 'application/json')
    return to_json(data)


def to_json(data):
    """Writes out python object to JSON.

    Includes special handling for Checkmate objects derived from MutableMapping
    """
    if isinstance(data, collections.MutableMapping) and hasattr(data, 'dumps'):
        return data.dumps(indent=4)
    return json.dumps(data, indent=4)

def try_int(string):
    try:
        return int(string)
    except ValueError:
        return string

HANDLERS = {
    'application/x-yaml': write_yaml,
    'application/json': write_json,
    'default': write_json
}


def formatted_response(uripath, with_pagination=False):
    """A function decorator that adds pagination information to the response
    header of a route/get/post/put function
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
            if with_pagination:
                _write_pagination_headers(
                    data,
                    kwargs.get('offset') or 0,
                    kwargs.get('limit') or 100,
                    bottle.response,
                    uripath,
                    kwargs.get('tenant_id', bottle.request.context.tenant)
                )
            if 'deployments' in uripath:
                expected_tenant = kwargs.get(
                    'tenant_id', bottle.request.context.tenant)
                if bottle.request.context.is_admin is True:
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
    """Ensures value contained in label is a positive integer."""
    value = kwargs.get(label, request.query.get(label))
    if value:
        kwargs[label] = int(value)
        if kwargs[label] < 0:
            raise ValueError


def _write_pagination_headers(data, offset, limit, response,
                              uripath, tenant_id):
    """Add pagination headers to the response body."""
    count = len(data.get('results'))
    if 'collection-count' in data:
        total = int(data.get('collection-count', 0))
    elif offset == 0 and (limit is None or limit > data['results'].count()):
        total = count
    else:
        total = None

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
            nextfmt = \
                '</%s/%s?limit=%d&offset=%d>; rel="next"; title="Next page"'
            response.add_header(
                "Link", nextfmt % (tenant_id, uripath, limit, offset + limit)
            )

        # Add Previous page link to http header
        if offset > 0 and (offset - limit) >= 0:
            prevfmt = '</%s/%s?limit=%d&offset=%d>; rel="previous"; \
            title="Previous page"'
            response.add_header(
                "Link", prevfmt % (tenant_id, uripath, limit, offset - limit)
            )

        # Add first page link to http header
        if offset > 0:
            firstfmt = '</%s/%s?limit=%d>; rel="first"; title="First page"'
            response.add_header(
                "Link", firstfmt % (tenant_id, uripath, limit))

        # Add last page link to http header
        if limit and limit < total:
            lastfmt = '</%s/%s?offset=%d>; rel="last"; title="Last page"'
            if limit and total % limit:
                last_offset = total - (total % limit)
            else:
                last_offset = total - limit
            response.add_header(
                "Link", lastfmt % (tenant_id, uripath, last_offset))


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

    #Use default
    return HANDLERS['default'](data, request, response)


def extract_sensitive_data(data, sensitive_keys=None):
    """Parses the dict passed in, extracting all sensitive data.

    Extracted data is placed into another dict, and returns two dicts; one
    without the sensitive data and with only the sensitive data.

    :param sensitive_keys: a list of keys considered sensitive
    """
    def key_match(key, sensitive_keys):
        """Determines whether or not key is in sensitive_keys."""
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
        """Returns split dict or list if it contains any sensitive fields."""
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
    """Converts a list of dictionary to a single dictionary.

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
    """Recursively merge two lists

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
            right.extend([None for _ in range(len(dest) -
                          len(source))])
        elif len(dest) < len(source):
            left.extend([None for _ in range(len(source) -
                         len(dest))])
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
    """Checks if string looks like it is an ssh key."""
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
    """Gets the body of a function (i.e. no definition line, and unindented."""
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
    """Ensure a context tenant_id is passed into decorated function

    A function decorator that ensures a context tenant_id is passed in to
    the decorated function as a kwarg
    """
    def wrapped(*args, **kwargs):
        """Internal function wrapped as a decorator."""
        if kwargs.get('tenant_id'):
            # Tenant ID is being passed in
            return fxn(*args, **kwargs)
        else:
            return fxn(
                *args, tenant_id=bottle.request.context.tenant, **kwargs)
    return wrapped


def support_only(types):
    """Ensures route is only accepted if content type is supported.

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
        if bottle.request.context.is_admin is True:
            LOG.debug("Admin account '%s' accessing '%s'",
                      bottle.request.context.username, bottle.request.path)
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
    """Tests if a provided value is a valid uuid."""
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
    """Writes a value into a dict building any intermediate keys."""
    parts = path.split('/')
    current = target
    for part in parts[:-1]:
        if part not in current:
            current[part] = current = {}
        else:
            current = current[part]
    current[parts[-1]] = value


def read_path(source, path):
    """Reads a value from a dict supporting a path as a key."""
    parts = path.strip('/').split('/')
    current = source
    for part in parts[:-1]:
        if part not in current:
            return
        current = current[part]
        if not isinstance(current, dict):
            return
    return current.get(parts[-1])


def is_evaluable(value):
    """Check if value is a function that can be passed to evaluate()."""
    try:
        return (value.startswith('=generate_password(') or
                value.startswith('=generate_uuid('))
    except AttributeError:
        return False


def generate_password(min_length=None, max_length=None, required_chars=None,
                      starts_with=string.ascii_letters, valid_chars=None):
    """Generates a password based on constraints provided

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
        password_length = max_length or min_length or 8

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


def check_all_output(params, find="ERROR"):
    """Detects 'find' string in params, returning a list of all matching lines

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
                           close_fds=on_posix)

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
        raise subprc.CalledProcessError(retcode, ' '.join(params),
                                        output='\n'.join(stdout),
                                        error_info='%s%s' % ('\n'.join(stderr),
                                        '\n'.join(found)))


def is_simulation(api_id):
    """Determine if the current object is in simulation."""
    return str(api_id).startswith('simulate')


def get_id(is_sim):
    """Generate id: prepend 'simulate' for simulations."""
    if is_sim:
        return 'simulate%s' % uuid.uuid4().hex[0:12]
    else:
        return uuid.uuid4().hex


def git_clone(repo_dir, url, branch="master"):
    """Do a git checkout of `head' in `repo_dir'."""
    return subprc.check_output(
        ['git', 'clone', url, repo_dir, '--branch', branch])


def git_tags(repo_dir):
    """Return a list of git tags for the git repo in `repo_dir'."""
    return subprc.check_output(
        ['git', 'tag', '-l'], cwd=repo_dir).split("\n")


def git_checkout(repo_dir, head):
    """Do a git checkout of `head' in `repo_dir'."""
    return subprc.check_output(['git', 'checkout', head], cwd=repo_dir)


def git_fetch(repo_dir, refspec, remote="origin"):
    """Do a git fetch of `refspec' in `repo_dir'."""
    return subprc.check_output(
        ['git', 'fetch', remote, refspec], cwd=repo_dir)


def git_pull(repo_dir, head, remote="origin"):
    """Do a git pull of `head' from `remote'."""
    return subprc.check_output(['git', 'pull', remote, head], cwd=repo_dir)


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
    """Checks limit param and resets it to max allowable if needed."""
    # So that we don't end up with a DoS due to unchecked limit:
    if limit is None or limit > 100 or limit < 0:
        LOG.warn('Request for tenant %s with limit of %s. Defaulting '
                 'limit to 100.', tenant_id, limit)
        return 100
    return limit


def get_ips_from_server(server, roles, primary_address_type='public'):
    """Extract ip addresses from a server object."""
    ip_addr = None
    result = {}
    addresses = server.addresses.get(primary_address_type, [])
    for address in addresses:
        if address['version'] == 4:
            ip_addr = address['addr']
            break
    if ((primary_address_type != 'public' and server.accessIPv4) or
            'rack_connect' in roles):
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


class Simulation(object):
    """Generic object used to set simulation attrs."""
    def __init__(self, *args, **kwargs):
        """Assigns arguments to attributes.  Kwargs sets key to attr name."""
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
    """Detects a password part of a URL and replaces it with *****."""
    try:
        parsed = urlparse.urlsplit(url)
        if parsed.password:
            return url.replace(':%s@' % parsed.password, ':*****@')
    except StandardError:
        pass
    return url
