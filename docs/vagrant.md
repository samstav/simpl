# Installing Checkmate Dev Environment via Vagrant
![Checkmate](https://github.rackspace.com/checkmate/rook/raw/master/rook/static/img/checkmate.png)

## Initial Setup

Follow these instructions to spin up an Ubuntu 12.04 VM with your current 
Checkmate code installed and running.  If installing onto a clean workstation you will 
also need the headers and compilers for your platform, for example OSX will require Xcode.

Install [Vagrant](http://vagrantup.com/) (make sure you have version >= v1.1)
and [VirtualBox](https://www.virtualbox.org/), then execute these commands:

    $ gem install berkshelf
    $ vagrant plugin install vagrant-berkshelf 
    $ vagrant plugin install vagrant-omnibus
    $ git clone git://github.rackspace.com/checkmate/checkmate.git
    $ vagrant up

Make sure you have ```vagrant-berkshelf``` greater than 1.2.0 and ```vagrant-omnibus``` greater than 1.0.2.

## Upgrade from librarian-chef

If you have used vagrant with checkmate previously, you have likely used `librarian-chef`
to download cookbooks. Since we are now using `berkshelf` you no longer need the cookbooks
directory, and need to update the VirtualBox image. To update the image, follow these steps.

    $ vagrant destroy
    $ vagrant box remove precise virtualbox
    $ vagrant up

You may also need to remove the directory `vagrant`.

Note that you can also use "vagrant-libvirt". If you are working on a Linux or compatible KVM System.
To get this to work with Vagrant-libvirt you will need to perform the following :

  $ vagrant plugin install vagrant-libvirt

Now you will need to download the image reference for the checkmate environment which can be found at : http://files.vagrantup.com/precise64.box
To get this box image you will need to execute :

  $ vagrant box add precise64 http://files.vagrantup.com/precise64.box

Then you will need to edit the newly downloaded box image such that it can be imported via vagrant-libvirt.
The process is faily easy though consumes a bunch of space on your system. If you navigate to the folder where the new box image was downloaded you can begin the process to create your own libvirt box for vagrant. There are Five easy steps to the process.

1. Convert the image your downloaded to a qcow2 `qemu-img convert -f vmdk -O qcow2 ~/.vagrant.d/boxes/precise64/virtualbox/box-disk1.img ~/box.img`.
2. Create metadata.json with the following `echo '{"provider": "libvirt", "format": "qcow2", "virtual_size": 80}' > metadata.json`
3. Create the base VagrantFile with the following 

        Vagrant.configure("2") do |config|
          config.vm.provider :libvirt do |libvirt|
            libvirt.driver = "qemu"
            libvirt.host = "localhost"
            libvirt.connect_via_ssh = false
            libvirt.username = "root"
            libvirt.storage_pool_name = "default"
          end
        end

4. Now tar all the things together to make your box. `tar cvzf precise.box ./metadata.json ./Vagrantfile ./box.img`
5. Finally add the new box to your vagrant environment `vagrant box add precise file:////location/to/the/tar/precise.box`

You may also need to remove the directory `vagrant`.

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

#### git in the VM

If you plan to work on code within the VM, you need to make sure your git config is setup locally within the repo.

    $ cd /vagrant
    $ git config user.name "John Doe"
    $ git config user.email "john.doe@rackspace.com"

If you have already done this on the host machine, you are good to go. Keep in minde that
any config you have set at a `--global` level on your host machine will not be seen from
within the VM.


## Working with berkshelf

To update the cookbooks, you will need to run the following.

    $ berks update <COOKBOOK>
