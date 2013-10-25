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

from checkmate import utils


def evaluate(obj, **kwargs):
    """Evaluates the passed in object using Checkmate syntax."""
    if isinstance(obj, dict):
        for key, value in obj.iteritems():
            value = evaluate(value, **kwargs)
            if key == 'if':
                return value not in [False, None]
            elif key == 'if-not':
                return value in [False, None]
            elif key == 'or':
                return any(evaluate(o, **kwargs) for o in value)
            elif key == 'and':
                return all(evaluate(o, **kwargs) for o in value)
            elif key == 'value':
                return get_from_path(value, **kwargs)
            elif key == 'exists':
                return path_exists(value, **kwargs)
            elif key == 'not-exists':
                return not path_exists(value, **kwargs)

        return obj
    elif isinstance(obj, list):
        return [evaluate(o, **kwargs) for o in obj]
    else:
        return obj


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
    except AttributeError:
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
    except AttributeError:
        return False
