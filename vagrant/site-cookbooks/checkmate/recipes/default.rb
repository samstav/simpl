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

%w{bundler knife-solo knife-solo_data_bag}.each do |pkg|
  gem_package pkg do
    action :upgrade
  end
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

#service "checkmate-queue" do
#  start_command "checkmate-queue START --with-ui"
#  stop_command "checkmate-queue STOP"
#  environment ({ 'CHECKMATE' => '/all/the/things',
#                 'YOURA' => 'dbag })
#end
