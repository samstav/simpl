from setuptools import setup, find_packages


# Provide URLs to Github projects if they're not pip-aware
gh = 'https://github.com'
github_projects = [
                   {'project': 'python-keystoneclient', 'user': 'openstack'},
                   {'project': 'pychef', 'user': 'calebgroom', 'version': '-0.2.dev'},
                   {'project': 'rackspace-monitoring', 'user': 'racker'},
#    The following are shoud be built from the github.rackspace checkmate org, which contains patched code
#    In stalls this by running pip install -r pip-requirements.txt
#                   {'project': 'python-novaclient', 'user': 'openstack'},
#                   {'project': 'python-clouddb', 'user': 'slizadel', 'version': '-.01'},
#                   {'project': 'openstack.compute', 'user': 'jacobian', 'version': '-2.0a1'},
#                   {'project': 'python-clouddns', 'user': 'rackspace'},
#                   {'project': 'SpiffWorkflow', 'user': 'ziadsawalha','branch': 'celery', 'version': '-0.3.2-rackspace'},
                   ]

github_urls = []
for p in github_projects:
    github_urls.append('https://github.com/%s/%s/tarball/%s#egg=%s%s' % (
                       p['user'], p['project'], p.get('branch', 'master'),
                       p['project'], p.get('version', '')))

setup(
    name='checkmate',
    description='Configuration management and orchestration',
    keywords='orchestration configuration automation rackspace openstack',
    version='0.2.0',
    author='Rackspace Cloud',
    author_email='checkmate@lists.rackspace.com',
    dependency_links=github_urls,
    install_requires=['bottle==0.10.11',
                      'celery-with-mongodb==3.0',
                      'eventlet==0.9.17',
                      'GitPython==0.3.2.RC1',
                      'Jinja2==2.6',
                      'openstack.compute==2.0a1',
                      'pam==0.1.4',
                      'paramiko==1.7.7.2',
                      'pycrypto==2.6',
                      #Note: python-clouddb would end up being ".01", but that 
                      #is not valid (with a leading ".") so we exclude it here.
                      'python-clouddb',
                      'python-novaclient==2012.2',
                      'python-cloudlb',
                      'python-keystoneclient',
                      'python-clouddns',
                      'python-cloudfiles',
                      'rackspace-monitoring',
                      'PyChef==0.2.dev',
                      'PyYAML==3.10',
                      'SpiffWorkflow==0.3.2-rackspace',
                      'SQLAlchemy==0.7.8',
                      'sqlalchemy-migrate==0.7.2',
                      'WebOb==1.2.2',
                      'prettytable==0.6',
                      ],
    entry_points={
        'console_scripts': [
          'checkmate-server=checkmate.server:main_func',
          'checkmate=checkmate.checkmate_client:main_func',
          'checkmate-queue=checkmate.checkmate_queue:main_func',
          'checkmate-database=checkmate.checkmate_database:main_func',
          'checkmate-simulation=checkmate.sample.checkmate_simulation:main_func',
        ]
    },
    tests_require=['nose', 'unittest2', 'mox', 'webtest', 'pep8', 'coverage'],
    packages=find_packages(exclude=['tests', 'bin', 'examples', 'doc',
            'checkmate.openstack.*']),
    include_package_data=True,
    package_data={
        '': ['*.yaml'],
    },
    data_files=[('tests/data', ['tests/data/simulator.json'])],
    license='Apache License (2.0)',
    classifiers=["Programming Language :: Python"],
    url='https://rackspace.github.com/checkmate/checkmate'
)
