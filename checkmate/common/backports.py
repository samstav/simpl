#    License: Python Software Foundation License
#
#         http://opensource.org/licenses/Python-2.0

"""Backports from stdlib > 2.7"""
from __future__ import print_function

import os
import tempfile
import sys
import warnings


class TemporaryDirectory(object):
    """Create and return a temporary directory.  This has the same
    behavior as tempfile.mkdtemp but can be used as a context manager.
    For example:
        with TemporaryDirectory() as tmpdir:
            ...
    Upon exiting the context, the directory and everthing contained
    in it are removed.
    """

    def __init__(self, suffix="", prefix=tempfile.template, dir=None):
        self.name = tempfile.mkdtemp(suffix, prefix, dir)
        self._closed = False

    def __enter__(self):
        return self.name

    def cleanup(self, _warn=False):
        if self.name and not self._closed:
            try:
                self._rmtree(self.name)
            except (TypeError, AttributeError) as ex:
                # Issue #10188: Emit a warning on stderr
                # if the directory could not be cleaned
                # up due to missing globals
                if "None" not in str(ex):
                    raise
                print("ERROR: {!r} while cleaning up {!r}".format(ex, self,),
                      file=sys.stderr)
                return
            self._closed = True
            if _warn:
                self._warn("Implicitly cleaning up {!r}".format(self),
                           Warning)

    def __exit__(self, exc, value, tb):
        self.cleanup()

    def __del__(self):
        # Issue a ResourceWarning if implicit cleanup needed
        self.cleanup(_warn=True)

    # XXX (ncoghlan): The following code attempts to make
    # this class tolerant of the module nulling out process
    # that happens during CPython interpreter shutdown
    # Alas, it doesn't actually manage it. See issue #10188
    _listdir = staticmethod(os.listdir)
    _path_join = staticmethod(os.path.join)
    _isdir = staticmethod(os.path.isdir)
    _remove = staticmethod(os.remove)
    _rmdir = staticmethod(os.rmdir)
    _os_error = os.error
    _warn = warnings.warn

    def _rmtree(self, path):
        # Essentially a stripped down version of shutil.rmtree.  We can't
        # use globals because they may be None'ed out at shutdown.
        for name in self._listdir(path):
            fullname = self._path_join(path, name)
            try:
                isdir = self._isdir(fullname)
            except self._os_error:
                isdir = False
            if isdir:
                self._rmtree(fullname)
            else:
                try:
                    self._remove(fullname)
                except self._os_error:
                    pass
        try:
            self._rmdir(path)
        except self._os_error:
            pass
