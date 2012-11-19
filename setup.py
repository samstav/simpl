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
    install_requires=['bottle==0.10.11',
                      'SQLAlchemy==0.7.8',
                      'sqlalchemy-migrate==0.7.2',
                      'WebOb==1.2.2',
                      'pymongo==2.3',
                      ],
    packages=find_packages(exclude=['vagrant', 'tests', 'examples', 'doc']),
    license='Apache License (2.0)',
    classifiers=["Programming Language :: Python"],
    url='https://rackspace.github.com/checkmate/rook'
)
