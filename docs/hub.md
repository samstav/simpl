# Overview
"[hub](http://defunkt.io/hub/) is a command-line wrapper for git that makes you better at GitHub."

- [Site](http://defunkt.io/hub/)
- [Source](https://github.com/defunkt/hub)

# Installation
#### install on OS X
    $ brew install hub

#### other systems
    $ curl http://defunkt.io/hub/standalone -sLo ~/bin/hub
    $ chmod +x ~/bin/hub

#### alias it as git
    $ alias git=hub

    $ git version
    git version 1.7.9
    hub version 1.8.4 
    
#### or run stand alone
    $ hub version
    git version 1.7.9
    hub version 1.8.4 

# Setup
By default `hub` is configured to use public github. To use github::enterprise, follow these steps.

1. Whitelist our domain: `git config --global --add hub.host github.rackspace.com`
2. Setup `https` as preferred protocol: `git config --global hub.protocol https`
3. Set `GITHUB_HOST` in your ENV (`~/.bash_profile`): `export GITHUB_HOST="github.rackspace.com"`

# Usage
`hub` assumes `origin` to be the actual upstream so this may change your workflow slightly. When cloning, `origin` must be the upstream for the following commands to work. `YOUR_REMOTE` will be your username from github.

`hub` opens creates many new features, and even overrides git commands. Keep in mind that all code must already be on github for most of these commands to work.

##### Submit a pull request (and attach to issue)
    $ git push YOUR_REMOTE feature_branch
    $ git pull-request [-i 1234]
    
Be careful to read the comments in the commit to be sure your pull request is going to and coming from the correct branch. 

##### Checkout a pull request to a branch for testing
The branch will be named as the `<user>_<feature_branch>`

    $ git checkout https://github.rackspace.com/checkmate/checkmate/pull/1234

##### Other
Other features are available that can be seen in the [docs](http://defunkt.io/hub/), or `man hub`.