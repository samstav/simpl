from setuptools import setup, find_packages
from ConfigParser import ConfigParser


def get_config():
    import os
    import __main__
    pwd = os.path.dirname(__file__)
    configfile = 'rook/rook.cfg'
    if pwd:
        configfile = '%s/%s' % (pwd, configfile)
    config = ConfigParser()
    config.read(configfile)
    return config


setup(
    name='rook',
    description='Checkmate Browser UI',
    keywords=('checkmate orchestration configuration automation rackspace '
              'openstack'),
    version=get_config().get("rook", "version"),
    author='Rackspace Cloud',
    author_email='checkmate@lists.rackspace.com',
    install_requires=[],  # let checkmate drive these
    packages=find_packages(exclude=['vagrant', 'tests', 'examples', 'doc']),
    include_package_data=True,
    license='Apache License (2.0)',
    classifiers=["Programming Language :: Python"],
    url='https://rackspace.github.com/checkmate/rook'
)
