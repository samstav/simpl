from setuptools import setup, find_packages


# Provide URLs to Github projects if they're not pip-aware
gh = 'https://github.com'
github_projects = [{'project': 'python-clouddns', 'user': 'rackspace'},
                   {'project': 'python-clouddb', 'user': 'slizadel'},
                   {'project': 'openstack.compute', 'user': 'jacobian'},
                   {'project': 'python-keystoneclient', 'user': 'openstack'},
                   {'project': 'python-novaclient', 'user': 'openstack'},
                   {'project': 'pychef', 'user': 'calebgroom'},
                   {'project': 'rackspace-monitoring', 'user': 'racker'},
                   {'project': 'SpiffWorkflow', 'user': 'ziadsawalha','branch': 'celery'}]

github_urls = []
for p in github_projects:
    github_urls.append('https://github.com/%s/%s/tarball/%s#egg=%s' % (
                       p['user'], p['project'], p.get('branch', 'master'),
                       p['project']))

setup(
    name='checkmate',
    description='Configuration management and orchestration',
    keywords='orchestration configuration automation rackspace openstack',
    version='0.2',
    author='Ziad Sawalha',
    author_email='ziad.sawalha@rackspace.com',
    dependency_links=github_urls,
    install_requires=['bottle',
                      'celery',
                      'GitPython',
                      'Jinja2',
                      'openstack.compute',
                      'paramiko',
                      'pycrypto',
                      'python-clouddb',
                      'python-novaclient',
                      'python-cloudlb',
                      'python-keystoneclient',
                      'python-clouddns',
                      'python-cloudfiles',
                      'pychef',
                      'pyyaml',
                      'SpiffWorkflow',
                      'sqlalchemy',
                      'sqlalchemy-migrate',
                      'webob',
                      ],
    scripts=['bin/checkmate', 'bin/checkmate-server', 'bin/checkmate-queue',
            'bin/checkmate-simulation'],
    tests_require=['nose', 'unittest2', 'mox', 'webtest'],
    packages=find_packages(exclude=['tests', 'bin', 'examples', 'doc',
            'checkmate.openstack.*']),
    include_package_data=True,
    license='Apache License (2.0)',
    classifiers=["Programming Language :: Python"],
    url='https://github.com/ziadsawalha/checkmate'
)
