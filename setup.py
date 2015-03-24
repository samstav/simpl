# Copyright (c) 2011-2015 Rackspace US, Inc.
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
Setup for Checkmate.

All dependencies are listed in:

- requirements.txt for production
- test-requirements.txt for test and development
"""

import ast
import re
import sys

import setuptools
from setuptools.command import test

from checkmate.common import setup as setup_tools

TestCommand = test.test

REQUIRES = setup_tools.parse_requirements()


if 'develop' in sys.argv:
    # For a developer install, do not lock dependency versions or overwrite
    # the virtual environment that the developer has set up, since that might
    # include updated forks and dependencies as part of the development process
    # ... but do warn about that
    _forked = setup_tools.parse_dependency_links()
    print (
        "**************       DEPENDENCY WARNING          ****************\n"
        "We are assuming that since you're running 'develop' that you know\n"
        "to install the forked dependencies from the correct forks. If not,\n"
        "you might want to run 'pip install -r requirements.txt' to install\n"
        "the following forks:\n\n  %s\n" % '\n  '.join(_forked))
    DEPENDENCYLINKS = []
else:
    # A non-developer install, so use the tested versions from requirements.txt
    DEPENDENCYLINKS = setup_tools.parse_dependency_links()


class Tox(TestCommand):

    """Use Tox for setup.py test command."""

    def __init__(self, *args, **kwargs):
        self.test_args = []
        self.test_suite = True
        test.test.__init__(self, *args, **kwargs)

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        # import here, cause outside the eggs aren't loaded
        import tox
        tox.cmdline(self.test_args)


def package_meta():
    """Read __init__.py for global package metadata.

    Do this without importing the package.
    """
    _version_re = re.compile(r'__version__\s+=\s+(.*)')
    _url_re = re.compile(r'__url__\s+=\s+(.*)')
    _license_re = re.compile(r'__license__\s+=\s+(.*)')

    with open('checkmate/__init__.py', 'rb') as chkinit:
        initcontent = chkinit.read()
        version = str(ast.literal_eval(_version_re.search(
            initcontent.decode('utf-8')).group(1)))
        url = str(ast.literal_eval(_url_re.search(
            initcontent.decode('utf-8')).group(1)))
        licencia = str(ast.literal_eval(_license_re.search(
            initcontent.decode('utf-8')).group(1)))
    return {
        'version': version,
        'license': licencia,
        'url': url,
    }

_check_meta = package_meta()


setuptools.setup(
    name='checkmate',
    description='Configuration management and orchestration',
    keywords='orchestration configuration automation rackspace openstack',
    version=_check_meta['version'],
    author='Rackspace Cloud',
    author_email='checkmate@lists.rackspace.com',
    dependency_links=DEPENDENCYLINKS,
    install_requires=REQUIRES,
    entry_points={
        'console_scripts': [
            'checkmate=checkmate.entry_points:client',
            'checkmate-queue=checkmate.entry_points:queue',
            'checkmate-server=checkmate.entry_points:server',
            'checkmate-simulation=checkmate.entry_points:simulation',
        ]
    },
    tests_require=['tox'],
    cmdclass={'test': Tox},
    packages=setuptools.find_packages(
        exclude=['tests', 'bin', 'examples', 'doc', 'checkmate.openstack.*']),
    include_package_data=True,
    package_data={
        '': ['*.yaml'],
    },
    data_files=[('checkmate', ['checkmate/patterns.yaml'])],
    license=_check_meta['license'],
    classifiers=["Programming Language :: Python"],
    url=_check_meta['url'],
)
