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
    version='0.0.1',
    author='Ziad Sawalha',
    author_email='ziad.sawalha@rackspace.com',
    install_requires=['celery', 'sqlalchemy', 'bottle', 'SpiffWorkflow'],
    tests_require=['nose', 'webob', 'unittest2'],
    dependency_links=github_urls,
    packages=find_packages(exclude=['tests', 'bin', 'data']),
    license='GPLv2',
    url='https://github.rackspace.com/ziadsawalha/checkmate'
)
