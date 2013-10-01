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
"""
Script file templating and management module.
"""
import copy
import json
import logging
import os
import urlparse

from jinja2 import BytecodeCache
from jinja2 import DictLoader
from jinja2.sandbox import ImmutableSandboxedEnvironment
from jinja2 import TemplateError
import yaml

from checkmate import exceptions
from checkmate.inputs import Input
from checkmate.keys import hash_SHA512
from checkmate import utils

CODE_CACHE = {}
LOG = logging.getLogger(__name__)


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


def register_scheme(scheme):
    """Use this to register a new scheme with urlparse and have it be
    parsed in the same way as http is parsed
    """
    for method in [s for s in dir(urlparse) if s.startswith('uses_')]:
        getattr(urlparse, method).append(scheme)

register_scheme('git')  # without this, urlparse won't handle git:// correctly


class CompilerCache(BytecodeCache):
    """Cache for compiled template code."""

    def load_bytecode(self, bucket):
        if bucket.key in CODE_CACHE:
            bucket.bytecode_from_string(CODE_CACHE[bucket.key])

    def dump_bytecode(self, bucket):
        CODE_CACHE[bucket.key] = bucket.bytecode_to_string()


def do_prepend(value, param='/'):
    """Prepend a string if the passed in string exists.

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


def evaluate(value):
    """Handle defaults with functions."""
    if isinstance(value, basestring):
        if value.startswith('=generate'):
            # TODO(zns): Optimize. Maybe have Deployment class handle
            # it
            value = utils.evaluate(value[1:])
    return value


def parse_url(value):
    """Parse a url into its components.

    :returns: Input parsed as url to support full option parsing

    returns a blank URL if none provided to make this a safe function
    to call from within a Jinja template which will generally not cause
    exceptions and will always return a url object
    """
    result = Input(value or '')
    result.parse_url()
    for attribute in ['certificate', 'private_key',
                      'intermediate_key']:
        if getattr(result, attribute) is None:
            setattr(result, attribute, '')
    return result


def preserve_linefeeds(value):
    """Escape linefeeds.

    To make templates work with both YAML and JSON, escape linefeeds instead of
    allowing Jinja to render them.
    """
    return value.replace("\n", "\\n").replace("\r", "")


def parse(template, **kwargs):
    """Parse template.

    :param template: the template contents as a string
    :param kwargs: extra arguments are passed to the renderer
    """
    template_map = {'template': template}
    env = ImmutableSandboxedEnvironment(loader=DictLoader(template_map),
                                        bytecode_cache=CompilerCache())
    env.filters['prepend'] = do_prepend
    env.filters['preserve'] = preserve_linefeeds
    env.json = json
    env.globals['parse_url'] = parse_url
    env.globals['patterns'] = get_patterns()
    deployment = kwargs.get('deployment')
    resource = kwargs.get('resource')
    defaults = kwargs.get('defaults', {})
    if deployment:
        if resource:
            fxn = lambda setting_name: evaluate(
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
            fxn = lambda setting_name: evaluate(
                utils.escape_yaml_simple_string(
                    deployment.get_setting(
                        setting_name, default=defaults.get(setting_name,
                                                           '')
                    )
                )
            )
    else:
        # noop
        fxn = lambda setting_name: evaluate(
            utils.escape_yaml_simple_string(
                defaults.get(setting_name, '')))
    env.globals['setting'] = fxn
    env.globals['hash'] = hash_SHA512

    minimum_kwargs = {
        'deployment': {'id': ''},
        'resource': {},
        'component': {},
        'clients': [],
    }
    minimum_kwargs.update(kwargs)

    template = env.get_template('template')
    try:
        result = template.render(**minimum_kwargs)
        #TODO(zns): exceptions in Jinja template sometimes missing
        #traceback
    except StandardError as exc:
        LOG.error(exc, exc_info=True)
        error_message = "Template rendering failed: %s" % exc
        raise exceptions.CheckmateException(error_message)
    except TemplateError as exc:
        LOG.error(exc, exc_info=True)
        error_message = "Template had an error: %s" % exc
        raise exceptions.CheckmateException(error_message)
    return result
