#
# Cookbook Name:: checkmate
# Recipe:: default
#
# Copyright 2012, Rackspace
#
# All rights reserved - Do Not Redistribute
#
::Chef::Recipe.send(:include, Opscode::OpenSSL::Password)

node.set_unless['checkmate']['rabbitmq']['password'] = secure_password

%w{git python-setuptools python2.7-dev python-dev vim}.each do |pkg|
  package pkg do
    action :upgrade
  end
end

execute "update_gem" do
  command "gem update --system"
end

%w{json mime-types mixlib-shellout bundler knife-solo knife-solo_data_bag}.each do |pkg|
  gem_package pkg do
    action :upgrade
  end
end

link "/usr/bin/knife" do
  to "/opt/vagrant_ruby/bin/knife"
end

python_pip "#{node['checkmate']['local_source']}/pip-requirements.txt" do
  options "-r"
  action :install
end

rabbitmq_user "guest" do
  action :delete
end

rabbitmq_vhost node['checkmate']['rabbitmq']['vhost'] do
  action :add
end

rabbitmq_user node['checkmate']['rabbitmq']['user'] do
  password node['checkmate']['rabbitmq']['password']
  action :add
end

rabbitmq_user node['checkmate']['rabbitmq']['user'] do
  vhost node['checkmate']['rabbitmq']['vhost']
  permissions "\".*\" \".*\" \".*\""
  action :set_permissions
end

directory node['checkmate']['local_path'] do
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

ENV['CHECKMATE_BROKER_USERNAME'] = node['checkmate']['broker_username']
ENV['CHECKMATE_BROKER_PASSWORD'] = node['checkmate']['broker_password']
ENV['CHECKMATE_BROKER_PORT'] = node['checkmate']['broker_port']
ENV['CHECKMATE_BROKER_HOST'] = node['checkmate']['broker_host']
ENV['CELERY_CONFIG_MODULE'] = node['checkmate']['celery_config_module']
ENV['CHECKMATE_CHEF_REPO'] = node['checkmate']['chef_repo']
ENV['CHECKMATE_CONNECTION_STRING'] = node['checkmate']['connection_string']

template "/etc/init.d/checkmate-queue" do
  source "checkmate-queue.erb"
  notifies :reload, "service[checkmate-queue]"
  owner "root"
  group "root"
  mode 0755
end

template "/etc/default/checkmate-queue" do
  source "checkmate-queue.default.erb"
  owner "root"
  group "root"
  mode 0644
end

user "checkmate" do
  comment "Checkmate"
  system true
  shell "/bin/false"
end

service "checkmate-queue" do
  action [ :start, :enable ]
end
