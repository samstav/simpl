# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant::Config.run do |config|
  # Lets lower the memory consumption some
  #config.vm.customize ["modifyvm", :id, "--memory", 256]

  # Every Vagrant virtual environment requires a box to build off of.
  config.vm.box = "precise"
  config.vm.box_url = "http://files.vagrantup.com/precise64.box"

  config.vm.provision :shell, :inline => "if [ \"$(chef-client --version |awk '{print $2}')\" != \"10.12.0\" ]; then bash <(wget http://chef.rackspacecloud.com/install-alt.sh -q --tries=10 -O -) -v 10.12.0-1 -r 2>> /dev/null; fi"

  config.vm.provision :chef_solo do |chef|
    chef.log_level = :debug
    chef.cookbooks_path = ["vagrant/cookbooks"]
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
    chef.add_recipe "rvm::user"
    chef.add_recipe "checkmate::vagrant"
    chef.add_recipe "checkmate::broker"
    chef.add_recipe "checkmate::worker"
    chef.add_recipe "checkmate::webui"

    chef.json = {
      :rvm => {
        :user_installs => [{
          :user => 'vagrant',
          :default_ruby => 'ruby-1.9.3-p125@checkmate',
          :gems => {
            'ruby-1.9.3-p125@checkmate' => [
              { 'name' => 'bundler' },
              { 'name' => 'chef',
                'version' => '10.12.0' },
              { 'name' => 'knife-solo',
                'version' => '0.0.13' },
              { 'name' => 'knife-solo_data_bag',
                'version' => '0.2.1' }
            ]
          }
        }]
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
          :args => '--with-ui --with-simulator --eventlet --debug 0.0.0.0:8080',
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
          :type => "mongodb",
        }
      },
      :build_essential => {
        :compiletime => true
      }
    }
  end

  config.vm.forward_port 8080, 8080
  config.vm.forward_port 5555, 5555
end
