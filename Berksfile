#!/usr/bin/env ruby
#^syntax detection

site :opscode

cookbook 'sysstat'
cookbook 'chef-client'
cookbook 'openssh'
cookbook 'python'
cookbook 'ntp'
cookbook 'sudo'
cookbook 'rsyslog'
cookbook 'newrelic'
cookbook 'jenkins', github: 'opscode-cookbooks/jenkins'

cookbook 'logstash',
  git: 'https://github.com/lusis/chef-logstash'
cookbook 'kibana',
  git: 'https://github.com/lusis/chef-kibana'
cookbook 'rvm',
  git: 'https://github.com/fnichol/chef-rvm',
  ref: '485e042818063dcf40e8da1404d9758fb26de65d'
cookbook 'mongodb',
  git: 'https://github.com/gondoi/chef-mongodb'
cookbook 'user',
  git: 'https://github.com/fnichol/chef-user'
cookbook 'rackspacecloud',
  git: 'https://github.com/rackspace-cookbooks/rackspacecloud'
cookbook 'checkmate',
  git: 'https://github.rackspace.com/Cookbooks/checkmate'
cookbook 'checkmate_dashboard',
  git: 'https://github.rackspace.com/Cookbooks/checkmate_dashboard.git'
cookbook 'checkmate_scheduledtasks',
  git: 'https://github.rackspace.com/Cookbooks/checkmate_scheduledtasks'
cookbook 'checkmate-repose',
  git: 'https://github.rackspace.com/checkmate/repose-cookbook'
cookbook 'diamond',
  git: 'https://github.com/damm/diamond.git',
  ref: '0.2.4'
cookbook 'redisio',
  git: 'https://github.com/brianbianco/redisio.git',
  branch: '2.0.0_wip'

# DEPRECATE ONCE WE RELEASE repose-cookbook
cookbook 'chef-repose',
  git: 'https://github.rackspace.com/jimm6286/chef-repose',
  tag: 'v1.0.25'
