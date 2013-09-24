# Copyright (c) 2011-2013 Rackspace Hosting
#
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
"""Deployment Inputs parser"""
import urlparse


def register_scheme(scheme):
    """Use this to register a new scheme with urlparse and have it be parsed
    in the same way as http is parsed
    """
    for method in [s for s in dir(urlparse) if s.startswith('uses_')]:
        getattr(urlparse, method).append(scheme)

register_scheme('git')  # without this, urlparse won't handle git:// correctly


class Input(str):
    """Class to handle inputs

    Treats all inputs as strings. Allows for 'url' type to extend string and
    still behave like a string.

    Example:

        i = Input({'url': 'http://test.com/', 'protocol': 'http'})
        print i, i.protocol, i.hostname
        >>> 'http://test.com/', 'http', 'test.com'

    """
    def __new__(cls, string):
        """init new instance and handle url type."""
        if isinstance(string, int):
            return string
        elif isinstance(string, dict):
            # Make the default string value that of the url
            value = string.get('url') or ''
            obj = super(Input, cls).__new__(cls, value)

            # Set provided values as attributes
            for key, value in string.items():
                setattr(obj, key, value)

            # Parse the url
            obj.parse_url()
        else:
            obj = super(Input, cls).__new__(cls, string)
        return obj

    def parse_url(self):
        """Parse the url and set attributes.

        Called automatically if this class is initialized with a dict.
        Can be called manually when we want the type to be parsed as a url.

        """
        parts = urlparse.urlparse(self)
        properties = [
            'fragment',
            'hostname',
            'netloc',
            'params',
            'password',
            'path',
            'port',
            'query',
            'scheme',
            'username',
        ]
        for key in properties:
            if not hasattr(self, key):
                setattr(self, key, getattr(parts, key))

        # Alias 'protocol' and 'scheme'
        if not hasattr(self, 'protocol'):
            setattr(self, 'protocol', getattr(self, 'scheme'))

        # Set missing attributes
        if not hasattr(self, 'url'):
            setattr(self, 'url', str(self))
        for attribute in ['certificate', 'private_key',
                          'intermediate_key']:
            if not hasattr(self, attribute):
                setattr(self, attribute, None)
