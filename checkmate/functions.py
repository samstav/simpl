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
"""
Blueprint functions

Functions that can be used in blueprints:
- if
- or
- and
- value: accepts URI-type values (ex. resoures://0/instance/ip)

"""
import urlparse

from checkmate.common import templating
from checkmate import exceptions
from checkmate import utils

PATTERNS = {'patterns': templating.get_patterns()}


def evaluate(obj, **kwargs):
    """Evaluates the passed in object using Checkmate sytnax."""
    if isinstance(obj, dict):
        for key, value in obj.iteritems():
            if key == 'if':
                return evaluate(value, **kwargs) not in [False, None]
            elif key == 'if-not':
                return evaluate(value, **kwargs) in [False, None]
            elif key == 'or':
                return any(evaluate(o, **kwargs) for o in value)
            elif key == 'and':
                return all(evaluate(o, **kwargs) for o in value)
            elif key == 'value':
                return get_value(value, **kwargs)
            elif key == 'exists':
                return path_exists(value, **kwargs)
            elif key == 'not-exists':
                return not path_exists(value, **kwargs)

        return obj
    elif isinstance(obj, list):
        return [evaluate(o, **kwargs) for o in obj]
    else:
        return obj


def get_value(value, **kwargs):
    """Parse value entry (supports URIs)."""
    if is_uri(value):
        return get_from_path(value, **kwargs)
    elif is_pattern(value):
        return get_pattern(value, PATTERNS)
    else:
        return value


def is_uri(value):
    """Quick check to see if we have a URI."""
    if isinstance(value, basestring):
        if '://' in value:
            try:
                parsed = urlparse.urlparse(value)
                return len(parsed.scheme) > 0
            except AttributeError:
                return False
    return False


def is_pattern(value):
    """Quick check to see if we have a pattern from the pattern library."""
    return (isinstance(value, basestring) and
            value.startswith("patterns.") and
            value[-1] != ".")


def parse(obj, **kwargs):
    """Evaluates the passed in object's values using Checkmate syntax."""
    if isinstance(obj, dict):
        return {k: evaluate(v, **kwargs) for k, v in obj.iteritems()}
    else:
        return obj


def get_from_path(path, **kwargs):
    """Find value using URL syntax."""
    if not path:
        return path
    try:
        parsed = urlparse.urlparse(path)
        focus = kwargs[parsed.scheme]
        if parsed.netloc or parsed.path:
            combined = '%s/%s' % (parsed.netloc, parsed.path)
            combined = combined.replace('//', '/').strip('/')
            return utils.read_path(focus, combined)
        else:
            return focus
    except KeyError:
        return path


def path_exists(path, **kwargs):
    """Check value exists using URL syntax."""
    if not path:
        return False
    try:
        parsed = urlparse.urlparse(path)
        focus = kwargs[parsed.scheme]
        if parsed.netloc or parsed.path:
            combined = '%s/%s' % (parsed.netloc, parsed.path)
            combined = combined.replace('//', '/').strip('/')
            return utils.path_exists(focus, combined)
        else:
            return False
    except KeyError:
        return False


def get_pattern(value, patterns):
    """Get pattern from pattern library."""
    pattern = utils.read_path(patterns, value.replace('.', '/'))
    if not isinstance(pattern, dict):
        if pattern is None:
            raise exceptions.CheckmateDoesNotExist(
                "Pattern '%s' does not exist" % value)
        else:
            raise exceptions.CheckmateException(
                "Pattern is not in valid format: %s" % value)
    if 'value' not in pattern:
        raise exceptions.CheckmateException(
            "Pattern is missing 'value' entry: %s" % value)
    return pattern['value']
