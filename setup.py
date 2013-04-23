'''
Setup for Checkmate

All dependencies are listed in:

- pip-requiremets.txt for production
- pip-test-requiremets.txt for test and development

'''
import os
import sys

from ConfigParser import ConfigParser
from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand

from checkmate.common import setup as setup_tools


requires = setup_tools.parse_requirements()
if 'develop' in sys.argv:
    print ("We are assuming that since you're developing you have the\n"
           "dependency repos set up for development as well. If not,\n"
           "run 'pip install -r pip-requirements.txt' to install them")
    dependency_links = []
else:
    dependency_links = setup_tools.parse_dependency_links()


class Tox(TestCommand):
    '''Use Tox for setup.py test command'''

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        #import here, cause outside the eggs aren't loaded
        import tox
        tox.cmdline(self.test_args)


def get_config():
    import __main__
    pwd = os.path.dirname(__file__)
    configfile = 'checkmate/checkmate.cfg'
    if pwd:
        configfile = '%s/%s' % (pwd, configfile)
    config = ConfigParser()
    config.read(configfile)
    return config


setup(
    name='checkmate',
    description='Configuration management and orchestration',
    keywords='orchestration configuration automation rackspace openstack',
    version=get_config().get("checkmate", "version"),
    author='Rackspace Cloud',
    author_email='checkmate@lists.rackspace.com',
    dependency_links=dependency_links,
    install_requires=requires,
    entry_points={
        'console_scripts': [
            'checkmate-server=checkmate.server:main_func',
            'checkmate=checkmate.checkmate_client:main_func',
            'checkmate-queue=checkmate.checkmate_queue:main_func',
            'checkmate-database=checkmate.checkmate_database:main_func',
            'checkmate-simulation=checkmate.sample.checkmate_simulation:'
                'main_func',
        ]
    },
    tests_require=['tox'],
    cmdclass={'test': Tox},
    packages=find_packages(exclude=['tests', 'bin', 'examples',
                                    'doc', 'checkmate.openstack.*']),
    include_package_data=True,
    package_data={
        '': ['*.yaml'],
    },
    #data_files=[('checkmate', ['checkmate/simulator.json'])],
    license='Apache License (2.0)',
    classifiers=["Programming Language :: Python"],
    url='https://rackspace.github.com/checkmate/checkmate'
)
