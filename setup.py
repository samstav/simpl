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
    print ("We are assuming that since you're developing you have the\n"
           "dependency repos set up for development as well. If not,\n"
           "run 'pip install -r requirements.txt' to install them")
    DEPENDENCYLINKS = []
else:
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

    with open('checkmate/__init__.py', 'rb') as f:
        f = f.read()
        version = str(ast.literal_eval(_version_re.search(
            f.decode('utf-8')).group(1)))
        url = str(ast.literal_eval(_url_re.search(
            f.decode('utf-8')).group(1)))
        license = str(ast.literal_eval(_license_re.search(
            f.decode('utf-8')).group(1)))
    return {
        'version': version,
        'license': license,
        'url': url,
    }

checkmeta = package_meta()


setuptools.setup(
    name='checkmate',
    description='Configuration management and orchestration',
    keywords='orchestration configuration automation rackspace openstack',
    version=checkmeta['version'],
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
    license=checkmeta['license'],
    classifiers=["Programming Language :: Python"],
    url=checkmeta['url'],
)
