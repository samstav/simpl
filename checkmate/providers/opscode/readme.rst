CHEF-LOCAL ARCHITECTURE
======================+

Chef-local is a multi-tenant, push solution for Chef which does not require a chef server.

Checkmate can use Chef as a configuration provider for configuring clients. It can use a Chef server if one is available. However, for simplicity and to address complete isolation between tenants, this design was developed that only uses
chef-solo (i.e. no need to install and manage a chef server).

Clients (systems managed by chef) will still get chef-client installed on them.

The design uses the following:

- chef-solo and chef-client installed on the checkmate server
- knife-solo - a Knife plugin that makes knife work better without a server
    https://github.com/matschaffer/knife-solo

Each managed environment gets its own, isolated folder containing:

- a chef kitchen (cookbooks, databags, nodes, a solr query index and other chef data)
- a private/public key pair (the public key gets deployed to the clients)
- separate chef configuration file and tmp folders

When operating knife in that folder, the environment is isolated from other folders.

The folder structure is:

/opt
 /checkmate
  /environments/
   /myEnv
    ├── private.pem
    ├── checkmate.pub
    └── /kitchen/
        ├── certificates
        ├── cookbooks
        ├── data_bags
        ├── nodes
        ├── roles
        ├── site-cookbooks
        └── solo.rb [-> linked to knife.rb]


INSTALLING CHEF FOR CHECKMATE CHEF-LOCAL
========================================

Note::

  Tested on Ubuntu 11.10 (also successfully configured on OSX, but not documented yet)

Starting with a clean Ununtu 11.10 system::

    # Add OpsCode package repo
    echo "deb http://apt.opscode.com/ `lsb_release -cs`-0.10 main" | sudo tee /etc/apt/sources.list.d/opscode.list
    sudo mkdir -p /etc/apt/trusted.gpg.d
    gpg --keyserver keys.gnupg.net --recv-keys 83EF826A
    gpg --export packages@opscode.com | sudo tee /etc/apt/trusted.gpg.d/opscode-keyring.gpg > /dev/null

    # Install Chef (blank)
    sudo apt-get update
    sudo apt-get install -y --force-yes opscode-keyring # permanent upgradeable keyring
    echo "chef chef/chef_server_url string none" | sudo debconf-set-selections && sudo apt-get install chef -y

    # Install Rubygems
    sudo apt-get install ruby ruby-dev libopenssl-ruby rdoc ri irb build-essential wget ssl-cert curl
    cd /tmp
    curl -O http://production.cf.rubygems.org/rubygems/rubygems-1.8.10.tgz
    tar zxf rubygems-1.8.10.tgz
    cd rubygems-1.8.10
    sudo ruby setup.rb --no-format-executable
    sudo gem install chef --no-ri --no-rdoc
    cd ..
    rm rubygems-1.8.10.tgz # your mother doesn't work here. clean up after yourself!
    rm -rf rubygems-1.8.10
    cd ~

    # install/set up checkmate with knife solo
    sudo gem install knife-solo --no-ri --no-rdoc

    cd ~ # or wherever you want to the root of your chef data to be
    git clone https://ziadsawalha@github.com/jarretraim/checkmate.git
    cd checkmate

    #Kill the noise! - create default knife configs so knife stops complaining
    knife configure -r . --defaults
    openssl genrsa -out ~/.chef/$USER.pem 2048
    mkdir cookbooks
    cd cookbooks
    git init
    touch .gitignore
    git add .gitignore
    git commit -m "Initial Commit"
    cd ..

    # write chef config file
    mkdir -p /tmp/chef-solo
    echo "# chef-solo -c chef-default.rb
    file_cache_path  \"`pwd`\"
    cookbook_path    [\"`pwd`/cookbooks\"]
    log_level        :info
    log_location     STDOUT
    ssl_verify_mode  :verify_none" > chef-default.rb

    #Test
    chef-solo -c chef-default.rb

Now we're going to set up an environments container::

    mkdir -p environments # this is your data folder (contains client environments)


New Customer Environment (called 'abc' for example)
---------------------------------------------------
::

    export ENAME=abc
    cd environments
    knife kitchen $ENAME # create a kitchen
    cd $ENAME

    # Generate key pair for this environment
    openssl genrsa -out private.pem 2048
    chmod 0600 private.pem
    ssh-keygen -y -f private.pem > checkmate.pub # this will be sent to servers
    #openssl rsa -in private.pem -pubout # BEGIN/END format

    # init cookbook repo
    cd cookbooks
    git init
    touch .gitignore
    git add .gitignore
    git commit -m "Initial Commit"
    cd ..

    echo "# chef-solo -c solo.rb
    file_cache_path  \"`pwd`\"
    cookbook_path    [\"`pwd`/cookbooks\", \"`pwd`/site-cookbooks\"]
    log_level        :info
    log_location     STDOUT
    ssl_verify_mode  :verify_none" > solo.rb

Note::

    cookbooks_path must be subdirectory of file_cache_path and naming the
    file solo.rb is safe as some calls default to that.


Operations (in environment folder)
----------------------------------

::

    # Getting recipes
    # get the recipes you want (ex. wordpress form OpsCode repo with dependencies)
    knife cookbook site install wordpress -c solo.rb

    #
    # Spin up new server and put checkmate.pub in authorized_keys
    #

    # Install chef on it and register it ({ip}.json will be created in nodes directory)
    knife prepare root@108.166.87.206 -i private.pem

    #
    # Deploy recipes to servers
    #
    # Option 1 - Modify nodes/[ip].json (add recipes: { "run_list": ["recipe[wordpress]"] })
    knife cook root@108.166.87.62 -i private.pem -c solo.rb
    # browse to http://108.166.87.62 to see your wordpress site

