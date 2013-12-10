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
import copy
import os
import urlparse
import yaml

from checkmate import exceptions
from checkmate import utils


def get_patterns():
    """Load regex patterns from patterns.yaml.

    These are effectively macros for blueprint authors to use.

    We cache this so we don't have to parse the yaml frequently. We always
    return a copy so we don't share the mutable between calls (and clients).
    """
    if hasattr(get_patterns, 'cache'):
        return copy.deepcopy(get_patterns.cache)
    path = os.path.join(os.path.dirname(__file__), 'patterns.yaml')
    patterns = yaml.safe_load(open(path, 'r'))
    get_patterns.cache = patterns
    return copy.deepcopy(patterns)

PATTERNS = {'patterns': get_patterns()}


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
        if parsed.scheme == 'settings':
            focus = get_setting_dict(parsed.netloc or parsed.path, **kwargs)
        else:
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


def eval_blueprint_fxn(value):
    """Handle defaults with functions."""
    if isinstance(value, basestring):
        if value.startswith('=generate'):
            # TODO(zns): Optimize. Maybe have Deployment class handle
            # it
            value = utils.evaluate(value[1:])
    return value


def get_setting_dict(setting, **kwargs):
    """Get setting from a deployment with resource context."""
    fxn = get_settings_fxn(**kwargs)
    value = fxn(setting)
    return {setting: value}


def get_settings_fxn(**kwargs):
    deployment = kwargs.get('deployment')
    resource = kwargs.get('resource')
    defaults = kwargs.get('defaults', {})
    if deployment:
        if resource:
            fxn = lambda setting_name: eval_blueprint_fxn(
                utils.escape_yaml_simple_string(
                    deployment.get_setting(
                        setting_name,
                        resource_type=resource['type'],
                        provider_key=resource['provider'],
                        service_name=resource['service'],
                        default=defaults.get(setting_name, '')
                    )
                )
            )
        else:
            fxn = lambda setting_name: eval_blueprint_fxn(
                utils.escape_yaml_simple_string(
                    deployment.get_setting(
                        setting_name, default=defaults.get(setting_name,
                                                           '')
                    )
                )
            )
    else:
        # noop
        fxn = lambda setting_name: eval_blueprint_fxn(
            utils.escape_yaml_simple_string(
                defaults.get(setting_name, '')))
    return fxn
