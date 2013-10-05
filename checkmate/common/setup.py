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
Utilities with minimum-dependencies for use in setup.py
"""
import logging
import os
import re
import sys

KNOWN_PACKAGE_TO_IMPORT_MAP = {
    "SpiffWorkflow": "SpiffWorkflow",
    "PyYAML": "yaml",
    "pycrypto": "Crypto",
    "PyChef": "chef",
    "PyGithub": "github",
}
LOG = logging.getLogger(__name__)


def get_reqs_from_files(requirements_files):
    """Get requirements from the first file that exists."""
    for requirements_file in requirements_files:
        if os.path.exists(requirements_file):
            with open(requirements_file, 'r') as file_handle:
                return file_handle.read().split('\n')
    return []


def parse_dependency_links(requirements_files=None):
    """Parse pip requirements and return a setup.py dependency_link list.

    Setup.py dependency_links inject alternate locations to find packages
    listed in requirements. This will return git repos for dependencies listed
    as git URLs.
    """
    if requirements_files is None:
        requirements_files = ['pip-requirements.txt', 'requirements.txt']

    dependency_links = []
    for line in get_reqs_from_files(requirements_files):
        # skip comments and blank lines
        if re.match(r'(\s*#)|(\s*$)', line):
            continue
        # lines with -e or -f need the whole line, minus the flag
        if re.match(r'\s*-[ef]\s+', line):
            dependency_links.append(re.sub(r'\s*-[ef]\s+', '', line))
        # lines that are only urls can go in unmolested
        elif re.match(r'\s*https?:', line):
            dependency_links.append(line)
    return dependency_links


def _parse_requirement_line(line):
    """Parses a line in a pip requirements file and returns modules (with
    version constraints if they exist).
    """
    parsed = None
    # skip comments and blank lines
    if re.match(r'(\s*#)|(\s*$)', line):
        return None

    # For the requirements list, we need to inject only the portion
    # after egg= so that distutils knows the package it's looking for
    # such as:
    # -e git://github.com/openstack/nova/master#egg=nova
    if re.match(r'\s*-e\s+', line):
        names = re.sub(r'\s*-e\s+.*#egg=(.*)$', r'\1', line).split('-')
        package = []
        version = []
        for index, name in enumerate(names):
            if index > 0 and '.' in name:
                # We've reached a version part (can't be the first)
                version = '-'.join(names[index:])
                break
            package.append(name)
        package_name = '-'.join(package)
        if version:
            entry = '%s==%s' % (package_name, version)
        else:
            entry = package_name
        parsed = entry
    # such as:
    # http://github.com/openstack/nova/zipball/master#egg=nova
    elif re.match(r'\s*https?:', line):
        parsed = re.sub(r'\s*https?:.*#egg=(.*)$', r'\1', line)
    # -f lines are for index locations, and don't get used here
    elif re.match(r'\s*-f\s+', line):
        pass
    # argparse is part of the standard library starting with 2.7
    # adding it to the requirements list breaks distro installs
    elif line == 'argparse' and sys.version_info >= (2, 7):
        pass
    else:
        parsed = line

    return parsed


def parse_requirements(requirements_files=None):
    """Parse pip requirements and return a setup.py dependency list.

    :returns: list of packages with version constraints
    """
    if requirements_files is None:
        requirements_files = ['pip-requirements.txt', 'requirements.txt']

    requirements = []
    for line in get_reqs_from_files(requirements_files):
        parsed = _parse_requirement_line(line)
        if parsed:
            requirements.append(parsed)

    return requirements


def required_imports(requirements_files=None):
    """Returns the imports for the required packages."""
    imports = []
    requirements = parse_requirements(requirements_files=requirements_files)
    for entry in requirements:
        try:
            parts = ''.join([c if c not in '<=>,' else " "
                             for c in entry]).split()
            lib_name = parts[0]
            version_constraints = entry[len(lib_name):]
            if lib_name in KNOWN_PACKAGE_TO_IMPORT_MAP:
                lib_name = KNOWN_PACKAGE_TO_IMPORT_MAP[lib_name]
            else:
                lib_name = parts[0].lower()
                lib_name = lib_name.replace('python', '').strip('-')
            imports.append((lib_name, version_constraints))
        except StandardError:
            LOG.warn("Error parsing requirement: %s", entry)
    return imports
