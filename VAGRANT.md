# Installing Checkmate Dev Environment via Vagrant
![Checkmate](https://github.rackspace.com/checkmate/checkmate/raw/master/checkmate/static/img/checkmate.png)

Follow these instructions to spin up an Ubuntu 12.04 VM with Checkmate
installed and running.

Install [Vagrant](http://vagrantup.com/) and [VirtualBox](https://www.virtualbox.org/),
then execute these commands:

    $ gem install librarian
    $ git clone git://github.rackspace.com/checkmate/checkmate.git
    $ cd checkmate/vagrant
    $ librarian-chef install
    $ cd ..
    $ vagrant up
    $ vagrant ssh

Once you are in the virtual machine, the checkmate repo is mounted at /vagrant.
Note that any changes to /vagrant will be reflected in your cloned copy of
checkmate.

To shutdown the VM:

    $ vagrant halt

To destroy the VM:

    $ vagrant destroy
