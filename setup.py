from setuptools import setup, find_packages


# Provide URLs to Github projects if they're not pip-aware
gh = 'https://github.com'
github_projects = [{'project': 'SpiffWorkflow', 'user': 'ziadsawalha',
                        'branch': 'celery'}]
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
    install_requires=['bottle',
                      'celery',
                      'Jinja2',
                      'openstack.compute',
                      'paramiko',
                      'pycrypto',
                      'python-clouddb',
                      'python-novaclient',
                      'pyyaml',
                      'SpiffWorkflow',
                      'sqlalchemy',
                      'sqlalchemy-migrate',
                      'webob',
                      ],
    scripts=['bin/checkmate', 'bin/checkmate-server', 'bin/checkmate-queue',
            'bin/checkmate-simulation'],
    tests_require=['nose', 'unittest2', 'mox', 'webtest'],
    dependency_links=github_urls,
    packages=find_packages(exclude=['tests', 'bin', 'examples', 'doc',
            'checkmate.openstack.*']),
    include_package_data=True,
    license='Apache License (2.0)',
    classifiers=["Programming Language :: Python"],
    url='https://github.com/ziadsawalha/checkmate'
)
