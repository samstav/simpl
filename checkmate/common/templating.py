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

"""Script file templating and management module."""

import base64
import json
import logging

from jinja2 import BytecodeCache
from jinja2 import DictLoader
from jinja2.sandbox import ImmutableSandboxedEnvironment
from jinja2 import TemplateError

from checkmate import exceptions
from checkmate import functions
from checkmate.inputs import Input
from checkmate.keys import hash_SHA512

CODE_CACHE = {}
LOG = logging.getLogger(__name__)


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


def noop(*args, **kwargs):
    """No operation function used as a stub for parsing templates."""
    return


def parse(template, extra_globals=None, **kwargs):
    """Parse template.

    :param template: the template contents as a string
    :param extra_globals: additional globals to include
    :param kwargs: extra arguments are passed to the renderer
    """
    template_map = {'template': template}
    env = ImmutableSandboxedEnvironment(loader=DictLoader(template_map),
                                        bytecode_cache=CompilerCache())
    env.filters['prepend'] = do_prepend
    env.filters['preserve'] = preserve_linefeeds
    env.filters['base64'] = base64.encodestring
    env.json = json
    env.globals['parse_url'] = parse_url
    env.globals['patterns'] = functions.get_patterns()

    env.globals['setting'] = functions.get_settings_fxn(**kwargs)
    env.globals['hash'] = hash_SHA512
    if extra_globals:
        env.globals.update(extra_globals)

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
