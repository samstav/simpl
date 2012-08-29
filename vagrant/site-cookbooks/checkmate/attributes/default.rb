default['checkmate']['path'] = "/var/checkmate"
default['checkmate']['venv_path'] = "/var/checkmate/venv"
default['checkmate']['queue_path'] = '/var/checkmate/venv/bin/checkmate-queue'
default['checkmate']['data_path'] = "/var/checkmate/data"
default['checkmate']['connection_string'] = "sqlite:////var/checkmate/data/db.sqlite"
default['checkmate']['connection_string_results'] = "sqlite:////var/checkmate/data/db.sqlite"
default['checkmate']['domain'] = 'example.com'
default['checkmate']['public_key'] = '~/.ssh/id_rsa.pub'
default['checkmate']['chef_path'] = '/var/checkmate/chef'
default['checkmate']['chef_local_path'] = '/var/checkmate/chef/local'
default['checkmate']['chef_repo'] = '/var/checkmate/chef/repo/chef-stockton'
default['checkmate']['use_data_bags'] = 'True'
default['checkmate']['celery']['force_execv'] = 'True'
default['checkmate']['broker']['username'] = "checkmate"
default['checkmate']['broker']['password'] = "checkmate"
default['checkmate']['broker']['port'] = "5672"
default['checkmate']['broker']['host'] = "localhost"
default['checkmate']['broker']['vhost'] = "checkmate"
default['checkmate']['broker']['url'] = sprintf("amqp://%s:%s@%s:%d/%s",
  node['checkmate']['broker']['username'],
  node['checkmate']['broker']['password'],
  node['checkmate']['broker']['host'],
  node['checkmate']['broker']['port'],
  node['checkmate']['broker']['vhost'])
default['checkmate']['celery']['module'] = 'checkmate.celeryconfig'
default['checkmate']['local_source'] = '/var/checkmate/src'
