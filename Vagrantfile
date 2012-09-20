# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant::Config.run do |config|
  # Lets lower the memory consumption some
  config.vm.customize ["modifyvm", :id, "--memory", 256]

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
    chef.add_recipe "rabbitmq"
    chef.add_recipe "mongodb::10gen_repo"
    chef.add_recipe "mongodb"
    chef.add_recipe "checkmate"
    chef.add_recipe "checkmate::vagrant"
    chef.add_recipe "checkmate::broker"
    chef.add_recipe "checkmate::worker"
    chef.add_recipe "checkmate::webui"

    chef.json = {
      :checkmate => {
        :git => {
          :src => "/vagrant",
          :reference => "master",
          :revision => "master"
        },
        :server => {
          :args => '--with-ui --eventlet --debug 0.0.0.0:8080',
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
          :username => "checkmate",
          :password => "Ch3ckm4te!",
          :host => "localhost",
          :port => 27017,
          :vhost => "checkmate"
        },
        :datastore => {
          :type => "sqlite",
          :mongodb_backend_settings => '{"host": "localhost", "database": "checkmate", "taskmeta_collection": "celery_task_meta"}'
        },
        :broker => {
          :type => "amqp",
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
