# Copyright (c) 2011-2015 Rackspace US, Inc.
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

"""Utility Classes."""

import collections
import copy
import json

from checkmate.common import schema
from checkmate.exceptions import CheckmateValidationException


class ExtensibleDict(collections.MutableMapping):

    """TODO: docstring."""

    def __init__(self, *args, **kwargs):
        obj = dict(*args, **kwargs)
        self.validate(obj)
        self._data = obj

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        return key in self._data

    def __iter__(self):
        return iter(self._data)

    def __getitem__(self, key):
        return self._data[self.__keytransform__(key)]

    def __setitem__(self, key, value):
        self._data[self.__keytransform__(key)] = value

    def __delitem__(self, k):
        del self._data[k]

    def __keytransform__(self, key):
        return key

    def __repr__(self):
        return self._data.__repr__()

    def __dict__(self):
        return self._data

    def __copy__(self):
        return type(self)(self._data.copy())

    def __deepcopy__(self, memo):
        return type(self)(copy.deepcopy(self._data, memo))

    def dumps(self, *args, **kwargs):
        """Dump json string of this class,

        Utility function to use since this is not detected as a dict by json
        """
        if 'default' not in kwargs:
            kwargs['default'] = lambda obj: obj.__dict__
        return json.dumps(self._data, *args, **kwargs)

    def update(self, data):
        """Update data of this class,

        This is required when creating a copy or deepcopy of this class
        """
        return self._data.update(data)

    @classmethod
    def validate(cls, obj):
        """Check schema and validate data. Raise error if errors exist.

        Call inspect if you want to check the data without raising and error.
        """
        errors = cls.inspect(obj)
        if errors:
            raise CheckmateValidationException("Invalid %s: %s" % (
                cls.__name__, '\n'.join(errors)))

    @classmethod
    def inspect(cls, obj):
        """Check schema and validate data.

        This can be called to inspect syntax without raising and error.
        Validate will raise an error if called.

        returns: list of errors
        """
        return schema.validate(obj, getattr(cls, '__schema__', None))
