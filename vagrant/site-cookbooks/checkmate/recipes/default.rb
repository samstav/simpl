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

execute "update_gem" do
  command "gem update --system"
end

%w{json mime-types mixlib-shellout bundler knife-solo knife-solo_data_bag}.each do |pkg|
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

python_virtualenv "#{node['checkmate']['path']}" do
  owner "checkmate"
  group "checkmate"
  action :create
end

git "#{node['checkmate']['local_source']}" do
  repository "/vagrant"
  reference "vagrant"
  revision "vagrant"
  action :sync
  user "checkmate"
  group "checkmate"
end

script "checkmate_deps" do
  interpreter "bash"
  user "checkmate"
  code <<-EOH
    . #{node['checkmate']['path']}/bin/activate
    pip install -r #{node['checkmate']['local_source']}/pip-requirements.txt
  EOH
end

script "checkmate-setup.py" do
  interpreter "bash"
  user "checkmate"
  cwd node['checkmate']['local_source']
  code <<-EOH
    . #{node['checkmate']['path']}/bin/activate
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

remote_file "/etc/init.d/checkmate-svr" do
  source "https://github.rackspace.com/cgroom/checkmate-deb/raw/master/noarch/etc/init.d/checkmate-svr"
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
  supports :reload => true, :start => true, :stop => true, :restart => true, :status => true
  action [ :start, :enable ]
end

service "checkmate-svr" do
  supports :reload => true, :start => true, :stop => true, :restart => true, :status => true
  action [ :start, :enable ]
end
