# Installing Checkmate Dev Environment via Vagrant
![Checkmate](https://github.rackspace.com/checkmate/checkmate/raw/master/checkmate/static/img/checkmate.png)

## Initial Setup

Follow these instructions to spin up an Ubuntu 12.04 VM with your current 
Checkmate code installed and running.  If installing onto a clean workstation you will 
also need the headers and compilers for your platform, for example OSX will require Xcode.

Install [Vagrant](http://vagrantup.com/) (make sure you have version >= v1.1)
and [VirtualBox](https://www.virtualbox.org/), then execute these commands:

    $ gem install berkshelf
    $ vagrant plugin install vagrant-berkshelf
    $ git clone git://github.rackspace.com/checkmate/checkmate.git
    $ vagrant up

## Working with Vagrant

Once you are in the virtual machine, the checkmate repo is mounted at /vagrant.
Note that any changes to /vagrant will be reflected in your cloned copy of
checkmate.

You can browse directly to the web interface at [http://localhost:8080](http://localhost:8080).
You can monitor celery tasks by using the web interface at [http://localhost:5555](http://localhost:5555). 

If any of the addresses above do not load correctly perform the following:
	
	$ vagrant ssh
	$ sudo /etc/init.d/checkmate-q stop && sudo /etc/init.d/checkmate-q start
	$ sudo /etc/init.d/checkmate-svr stop && sudo /etc/init.d/checkmate-svr start

To login to the VM:

    $ vagrant ssh

To re-run the Chef configuration process:

    $ vagrant provision

To reboot and re-run the Chef configuration process:

    $ vagrant reload

To shutdown the VM:

    $ vagrant halt

To destroy the VM:

    $ vagrant destroy

To modify any of the attributes, set the value in the chef.json hash in `Vagrantfile`.

## Inside the VM

Here are a few quick notes about what you'll find inside the VM:

* When you SSH into the VM, the vagrant user switches you to the checkmate user, sources /etc/default/checkmate
  and sources the Checkmate virtual environment (typically /opt/checkmate/bin/activate).
* The checkmate user can sudo without a password.

## Working with berkshelf

To update the cookbooks, you will need to run the following.

    $ berks update <COOKBOOK>
