# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  # Lets lower the memory consumption some
  #config.vm.customize ["modifyvm", :id, "--memory", 256]

  config.vm.define :cm_vm do |cm_vm|
    # Every Vagrant virtual environment requires a box to build off of.
    cm_vm.vm.box = "precise"
    cm_vm.vm.box_url = "http://files.vagrantup.com/precise64.box"
    cm_vm.vm.network :private_network, :ip => "192.168.122.69"
    
    config.vm.provider :libvirt do |libvirt, override|
      override.vm.box_url = "https://dl.dropboxusercontent.com/u/50757999/libvirtubuntubox.box"
      #NOTE the IP address should be relevant to your system
      override.vm.network :private_network, :ip => "192.168.122.69"
      libvirt.driver = "qemu"
      libvirt.host = %x[hostname].strip
      libvirt.connect_via_ssh = false
      libvirt.username = "root"
      libvirt.storage_pool_name = "default"
    end
  end

  config.omnibus.chef_version = :latest
  config.berkshelf.enabled = true

  config.vm.provision :chef_solo do |chef|
    chef.log_level = :debug
    #chef.roles_path = "vagrant/roles"
    #chef.data_bags_path = "vagrant/data_bags"
    chef.add_recipe "apt"
    chef.add_recipe "openssl"
    chef.add_recipe "build-essential"
    chef.add_recipe "python"
    #chef.add_recipe "rabbitmq"
    chef.add_recipe "mongodb::10gen_repo"
    chef.add_recipe "mongodb"
    chef.add_recipe "checkmate"
    chef.add_recipe "rvm::vagrant"
    chef.add_recipe "rvm::user"
    chef.add_recipe "checkmate::vagrant"
    chef.add_recipe "checkmate::redis-master"
    chef.add_recipe "checkmate::broker"
    chef.add_recipe "checkmate::datastore"
    chef.add_recipe "checkmate::worker"
    chef.add_recipe "checkmate::svr_instances"

    chef.json = {
      :rvm => {
        :version => "1.17.10",
        :branch => "none",
        :installer_url => "https://raw.github.com/wayneeseguin/rvm/master/binscripts/rvm-installer",
        :user_installs => [{
          :user => 'vagrant',
          :default_ruby => 'ruby-1.9.3@checkmate',
          :gems => {
            'ruby-1.9.3-p125@checkmate' => [
              { 'name' => 'bundler' },
              { 'name' => 'chef',
                'version' => '11.4.0' },
              { 'name' => 'librarian',
                'version' => '0.0.26'},
              { 'name' => 'berkshelf',
                'version' => '2.0.4'},
              { 'name' => 'knife-solo',
                'version' => '0.2.0' },
              { 'name' => 'knife-solo_data_bag',
                'version' => '0.3.2' }
            ]
          }
        }],
        :vagrant => {
          :system_chef_solo => '/usr/bin/chef-solo',
          :system_chef_client => '/usr/bin/chef-client'
        }
      },
      :checkmate => {
        :user => {
          :name => 'vagrant',
        },
        :group => {
          :name => 'vagrant',
        },
        :source => {
          :method => 'develop',
          :dev_source => '/vagrant'
        },
        :git => {
          :src => '/vagrant',
          :reference => 'master',
          :revision => 'master',
          :chef_stockton => {
            :src => 'git://github.rackspace.com/checkmate/chef-stockton.git',
          },
        },
        :server => {
          :args => '--with-ui --with-simulator --eventlet --debug --logconfig=/etc/checkmate/server-log.conf 0.0.0.0:8080',
        },
        :celeryd => {
           :loglevel => 'DEBUG',
        },
        :amqp => {
          :username => "checkmate",
          :password => "Ch3ckm4te!",
          :host => "localhost",
          :port => 5672,
          :vhost => "checkmate"
        },
        :mongodb => {
          :username => "vagrant",
          :password => "Ch3ckm4te!",
          :host => "localhost",
          :port => 27017,
          :vhost => "checkmate"
        },
        :datastore => {
          :type => "mongodb",
          :mongodb_backend_settings => '{"host": "localhost", "database": "checkmate", "taskmeta_collection": "celery_task_meta"}'
        },
        :broker => {
          :type => "redis",
        }
      },
      :build_essential => {
        :compiletime => true
      }
    }
  end

  config.vm.network :forwarded_port, guest: 8080, host: 8080
  config.vm.network :forwarded_port, guest: 5555, host: 5555
end
