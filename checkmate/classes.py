""" Utility CLasses """
import collections
import json

from checkmate.common import schema
from checkmate.exceptions import CheckmateValidationException


class ExtensibleDict(collections.MutableMapping):

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

    def dumps(self, *args, **kwargs):
        """Dump json string of this class

        Utility function to use since this is not detected as a dict by json
        """
        if 'default' not in kwargs:
            kwargs['default'] = lambda obj: obj.__dict__
        return json.dumps(self._data, *args, **kwargs)

    @classmethod
    def validate(cls, obj):
        errors = schema.validate(obj, None)

        if errors:
            raise CheckmateValidationException("Invalid %s: %s" % (
                    cls.__name__, '\n'.join(errors)))