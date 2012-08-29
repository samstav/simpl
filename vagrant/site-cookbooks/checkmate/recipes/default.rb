#
# Cookbook Name:: checkmate
# Recipe:: default
#
# Copyright 2012, Rackspace
#
# All rights reserved - Do Not Redistribute
#
::Chef::Recipe.send(:include, Opscode::OpenSSL::Password)

node.set_unless['checkmate']['broker']['password'] = secure_password

user "checkmate" do
  comment "Checkmate"
  shell "/bin/bash"
  home "/home/checkmate"
  supports :manage_home => true
end

%w{git python-setuptools python2.7-dev python-dev vim}.each do |pkg|
  package pkg do
    action :upgrade
  end
end

%w{bundler knife-solo knife-solo_data_bag}.each do |pkg|
  gem_package pkg do
    action :upgrade
  end
end

directory "#{node['checkmate']['path']}" do
  owner "checkmate"
  group "checkmate"
  mode "0755"
  action :create
end

python_virtualenv "#{node['checkmate']['venv_path']}" do
  owner "checkmate"
  group "checkmate"
  action :create
end

=begin
python_pip "#{node['checkmate']['local_source']}/pip-requirements.txt" do
  virtualenv "#{node['checkmate']['venv_path']}"
  options "-r"
  action :install
end
=end

git "#{node['checkmate']['local_source']}" do
  repository /vagrant
  reference "master"
  action :sync
  user "checkmate"
  group "checkmate"
end

script "checkmate-setup.py" do
  interpreter "bash"
  user "checkmate"
  cwd "/var/checkmate/src"
  code <<-EOH
  . /var/checkmate/venv/bin/activate
  python setup.py install
  EOH
end

rabbitmq_user "guest" do
  action :delete
end

rabbitmq_vhost node['checkmate']['broker']['vhost'] do
  action :add
end

rabbitmq_user node['checkmate']['broker']['username'] do
  password node['checkmate']['broker']['password']
  action :add
end

rabbitmq_user node['checkmate']['broker']['username'] do
  vhost node['checkmate']['broker']['vhost']
  permissions "\".*\" \".*\" \".*\""
  action :set_permissions
end

directory node['checkmate']['path'] do
  recursive true
end
directory node['checkmate']['chef_repo'] do
  recursive true
end

git node['checkmate']['chef_repo'] do
  repository "git://github.rackspace.com/checkmate/chef-stockton.git"
  reference "master"
  action :sync
end

remote_file "/etc/init.d/checkmate-q" do
  source "https://github.rackspace.com/cgroom/checkmate-deb/raw/master/noarch/etc/init.d/checkmate-q"
  owner "root"
  group "root"
  mode 0755
end

template "/etc/default/checkmate" do
  source "checkmate.default.erb"
  owner "root"
  group "root"
  mode 0644
end

service "checkmate-q" do
  action [ :start, :enable ]
end
