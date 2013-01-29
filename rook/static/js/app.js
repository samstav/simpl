//Support for different URL for checkmate server in chrome extension
var is_chrome_extension = navigator.userAgent.toLowerCase().indexOf('chrome') > -1 && chrome && chrome.extension;
var checkmate_server_base = is_chrome_extension ? 'http://localhost\\:8080' : '';

//Load AngularJS
var checkmate = angular.module('checkmate', ['checkmate.filters', 'checkmate.services', 'checkmate.directives', 'ngResource', 'ngSanitize', 'ngCookies', 'ui', 'ngLocale']);

//Load Angular Routes
checkmate.config(['$routeProvider', '$locationProvider', '$httpProvider', function($routeProvider, $locationProvider, $httpProvider) {
  // Static Paths
  $routeProvider.
  when('/', {
    templateUrl: '/partials/home.html',
    controller: StaticController
  }).
  when('/index.html', {
    templateUrl: '/partials/home.html',
    controller: StaticController
  }).
  when('/readme', {
    templateUrl: '/partials/readme.html',
    controller: StaticController
  }).
  when('/ui/build', {
    template: '<calculator/>',
    controller: StaticController
  });

  // New UI - static pages
  $routeProvider.
  when('/deployments/default', {
    templateUrl: '/partials/managed-cloud-wordpress.html',
    controller: DeploymentManagedCloudController
  }).when('/deployments/new', {
    templateUrl: '/partials/deployment-new-remote.html',
    controller: DeploymentNewRemoteController
  }).when('/:tenantId/deployments/new', {
    templateUrl: '/partials/deployment-new-remote.html',
    controller: DeploymentNewRemoteController,
    reloadOnSearch: false
  }).
  when('/deployments/wordpress-stacks', {
    templateUrl: '/partials/wordpress-stacks.html',
    controller: StaticController
  });

  // New UI - dynamic, tenant pages
  $routeProvider.
  when('/:tenantId/workflows/:id/status', {
    templateUrl: '/partials/workflow_status.html',
    controller: WorkflowController
  }).
  when('/:tenantId/workflows/:id', {
    templateUrl: '/partials/workflow.html',
    controller: WorkflowController,
    reloadOnSearch: false
  }).
  when('/:tenantId/workflows', {
    templateUrl: '/partials/workflows.html',
    controller: WorkflowListController
  }).
  when('/:tenantId/blueprints', {
    templateUrl: '/partials/blueprints-remote.html',
    controller: BlueprintRemoteListController
  }).
  when('/:tenantId/deployments', {
    templateUrl: '/partials/deployments.html',
    controller: DeploymentListController
  }).
  when('/:tenantId/deployments/:id', {
    controller: DeploymentController,
    templateUrl: '/partials/deployment.html'
  }).
  when('/:tenantId/providers', {
    controller: ProviderListController,
    templateUrl: '/partials/providers.html'
  }).
  when('/:tenantId/environments', {
    controller: EnvironmentListController,
    templateUrl: '/partials/environments.html'
  }).when('/404', {
    controller: StaticController,
    templateUrl: '/partials/404.html'
  }).otherwise({
    controller: StaticController,
    templateUrl: '/partials/404.html'
  });


  $locationProvider.html5Mode(true);
  // Hack to get access to them later
  checkmate.config.header_defaults = $httpProvider.defaults;
  $httpProvider.defaults.headers.common['Accept'] = "application/json";
  $httpProvider.defaults.headers.post['Content-Type'] = "application/json;charset=utf-8";

}]);

/*
Scope variables that control the Checkmate UI:
- angular.element('header').scope().showHeader = true/false
- angular.element('header').scope().showSearch = true/false

- angular.element('#leftControls').scope().showControls = true/false

- angular.element('.summaries').scope().showSummaries = true
- angular.element('.summaries').scope().showStatus = true

- angular.element('footer').scope().showFooter = true/false

*/

//Loads static content into body
function StaticController($scope, $location) {
  console.log("Loading static file " + $location.path());
  $scope.showHeader = false;
  $scope.showStatus = false;
}

//Loads external page
function ExternalController($window, $location) {
  console.log("Loading external URL " + $location.absUrl());
  $window.location.href = $location.absUrl();
}

//Root controller that implements authentication
function AppController($scope, $http, $location, $resource) {
  $scope.showHeader = true;
  $scope.showStatus = false;
  $scope.auth = {
      username: '',
      tenantId: '',
      expires: ''
    };

  $scope.navigate = function(url) {
    $location.path(url);
  };

  $scope.notify = function(message) {
    $('.bottom-right').notify({
        message: { text: message }, fadeOut: {enabled: true, delay: 5000},
        type: 'bangTidy'
      }).show();
  };

  //Call this with an http response for a generic error message
  $scope.show_error = function(response) {
    var error = response;
    var info = {data: error.data,
                status: error.status,
                title: "Error",
                message: "There was an error executing your request:"};
    if (typeof error.data == "object" && 'description' in error.data)
        info.message = error.data.description;
    $scope.$root.error = info;
    $('#modalError').modal('show');
  };

  //Accepts subset of auth data. We use a subset so we can store it locally.
  $scope.accept_auth_data = function(response) {
      $scope.auth.catalog = response;
      $scope.auth.username = response.access.user.name;
      $scope.auth.tenantId = response.access.token.tenant.id;
      checkmate.config.header_defaults.headers.common['X-Auth-Token'] = response.access.token.id;
      checkmate.config.header_defaults.headers.common['X-Auth-Source'] = response.auth_url;
      var expires = new Date(response.access.token.expires);
      var now = new Date();
      if (expires < now) {
        $scope.auth.expires = 'expired';
        $scope.auth.loggedIn = false;
      } else {
        $scope.auth.expires = expires - now;
        $scope.auth.loggedIn = true;
      }
  };

  // Restore login from session
  var auth = localStorage.getItem('auth');
  if (auth !== undefined && auth !== null)
    auth = JSON.parse(auth);
  if (auth !== undefined && auth !== null && auth != {} && 'access' in auth && 'token' in auth.access) {
    expires = new Date(auth.access.token.expires);
    now = new Date();
    if (expires.getTime() > now.getTime()) {
      auth.loggedIn = true;
      $scope.accept_auth_data(auth);
    } else {
      $scope.auth.loggedIn = false;
    }
  } else {
    $scope.auth.loggedIn = false;
  }

  // Bind to logon modal
  $scope.bound_creds = {
    username: '',
    password: '',
    apikey: '',
    auth_url: "https://identity.api.rackspacecloud.com/v2.0/tokens" //default
  };

  $scope.refresh = function() {
  };

  $scope.handleSpace = function() {
  };

  // Display log in prompt
  $scope.loginPrompt = function(success_callback, failure_callback) {
    var modal = $('#modalAuth');
    modal.modal({
      keyboard: false,
      show: true
    });

    modal[0].success_callback = success_callback;
    modal[0].failure_callback = failure_callback;
    modal.on('shown', function () {
      $('input:text:visible:first', this).focus();
    });
    modal.modal('show');
  };

  // Log in using credentials delivered through bound_credentials
  $scope.logIn = function() {
    var username = $scope.bound_creds.username;
    var password = $scope.bound_creds.password;
    var apikey = $scope.bound_creds.apikey;
    var auth_url = $scope.bound_creds.auth_url;
    var data;
    if (apikey) {
       data = JSON.stringify({
        "auth": {
          "RAX-KSKEY:apiKeyCredentials": {
            "username": username,
            "apiKey": apikey
          }
        }
      });
     } else if (password) {
       data = JSON.stringify({
          "auth": {
            "passwordCredentials": {
              "username": username,
              "password": password
            }
          }
        });
     } else {
      return false;
     }

    if (auth_url === undefined || auth_url === null || auth_url.length === 0) {
      headers = {};  // Not supported on server, but we should do it
    } else {
      headers = {"X-Auth-Source": auth_url};
    }
    return $.ajax({
      type: "POST",
      contentType: "application/json; charset=utf-8",
      headers: headers,
      dataType: "json",
      url: is_chrome_extension ? auth_url : "/authproxy",
      data: data
    }).success(function(json) {
      $('#modalAuth').modal('hide');
      //Parse data. Keep only a subset to store in local storage
      var keep = {access: {token: json.access.token, user: json.access.user}};
      keep.auth_url = auth_url;  // save for later
      regions = _.union.apply(this, _.map(json.access.serviceCatalog, function(o) {return _.map(o.endpoints, function(e) {return e.region;});}));
      if (regions.indexOf(json.access.user['RAX-AUTH:defaultRegion']) == -1)
        regions.push(json.access.user['RAX-AUTH:defaultRegion']);
      keep.access.regions = _.compact(regions);
      localStorage.setItem('auth', JSON.stringify(keep));
      $scope.accept_auth_data(keep);
      $scope.bound_creds = {
          username: '',
          password: '',
          apikey: '',
          auth_url: "https://identity.api.rackspacecloud.com/v2.0/tokens"
        };
      $scope.notify("Welcome, " + $scope.auth.username + "! You are logged in");
      if (typeof $('#modalAuth')[0].success_callback == 'function') {
          $('#modalAuth')[0].success_callback();
          delete $('#modalAuth')[0].success_callback;
          delete $('#modalAuth')[0].failure_callback;
        }
      else
        $scope.$apply();
      $scope.$broadcast('logIn');
    }).error(function(response) {
      if (typeof $('#modalAuth')[0].failure_callback == 'function') {
          $('#modalAuth')[0].failure_callback();
          delete $('#modalAuth')[0].success_callback;
          delete $('#modalAuth')[0].failure_callback;
        }
      $("#auth_error_text").html(response.statusText + ". Check that you typed in the correct credentials.");
      $("#auth_error").show();
    });
  };

  $scope.logOut = function() {
    $scope.auth.username = '';
    $scope.auth.catalog = null;
    localStorage.removeItem('auth');
    $scope.auth.loggedIn = false;
    delete checkmate.config.header_defaults.headers.common['X-Auth-Token'];
    delete checkmate.config.header_defaults.headers.common['X-Auth-Source'];
    $location.path('/');
  };


  // Utility Functions
  console.log("Getting api version");
  var api = $resource((checkmate_server_base || '') + '/version');
  api.get(function(data, getResponseHeaders){
    $scope.api_version = data.version;
    console.log("Got api version: " + $scope.api_version);
  });

  console.log("Getting rook version");
  var rook = $resource((checkmate_server_base || '') + '/rookversion');
  rook.get(function(rookdata, getResponseHeaders){
      $scope.rook_version = rookdata.version;
      console.log("Got rook version: " + $scope.rook_version);
      console.log("Got version: " + $scope.api_version);
      $scope.$root.simulator = getResponseHeaders("X-Simulator-Enabled");
  });

  //Check for a supported account
  $scope.is_unsupported_account = function() {
    var roles = [];
    if ($scope.auth.loggedIn === true)
        roles = $scope.auth.catalog.access.user.roles || [];
    return _.any(roles, function(role) {return role.name == "rack_connect";});
  };

  //Check for a service level
  $scope.is_managed_account = function() {
    var roles = [];
    if ($scope.auth.loggedIn === true)
        roles = $scope.auth.catalog.access.user.roles || [];
    return _.any(roles, function(role) {return role.name == "rax_managed";});
  };

  $scope.generatePassword = function() {
      if (parseInt(navigator.appVersion, 10) <= 3) {
          $scope.notify("Sorry this only works in 4.0+ browsers");
          return true;
      }

      var length = 10;
      var sPassword = "";

      var noPunction = true;
      for (i=0; i < length; i++) {

          var numI = $scope.getPwdRandomNum();
          //Always have a letter for the first character.
          while (i===0 && (numI <= 64 || ((numI >=91) && (numI <=96)))) { numI = $scope.getPwdRandomNum(); }
          //Only allow letters and numbers for all other characters.
          while (((numI >=58) && (numI <=64)) || ((numI >=91) && (numI <=96))) { numI = $scope.getPwdRandomNum(); }

          sPassword = sPassword + String.fromCharCode(numI);
      }
      return sPassword;
  };

  $scope.getPwdRandomNum = function() {

      // between 0 - 1
      var rndNum = Math.random();

      // rndNum from 0 - 1000
      rndNum = parseInt(rndNum * 1000, 10);

      // rndNum from 33 - 127
      rndNum = (rndNum % 75) + 48;

      return rndNum;
  };

  $scope.encodeURIComponent = function(data) {
    return encodeURIComponent(data);
  };

}

function NavBarController($scope, $location) {
  $scope.feedback = "";
  $scope.email = "";

  // Send feedback to server
  $scope.send_feedback = function() {
    data = JSON.stringify({
        "feedback": {
            "request": $scope.feedback,
            "email": $scope.email,
            "username": $scope.auth.username,
            "tenantId": $scope.auth.tenantId,
            "location": $location.absUrl(),
            "auth": $scope.auth,
            "api_version": $scope.api_version,
            "rook_version": $scope.rook_version
            }
          });
    headers = checkmate.config.header_defaults.headers.common;
    return $.ajax({
      type: "POST",
      contentType: "application/json; charset=utf-8",
      headers: headers,
      dataType: "json",
      url: "https://checkmate.rackspace.com/feedback",
      data: data
    }).success(function(json) {
        $('.dropdown.open .dropdown-toggle').dropdown('toggle');
        $scope.notify("Feedback received. Thank you!");
        $scope.feedback = "";
        $('#feedback').val('');
        $("#feedback_error").hide();
    }).error(function(response) {
      $("#feedback_error_text").html(response.statusText);
      $("#feedback_error").show();
    });
  };

}

function ActivityFeedController($scope, $http, items) {
  $scope.parse_event = function(event, key) {
    var parsed = {
      key: event.id,
      id: event.id,
      when: event.created_at,
      actor: event.actor.login,
      actor_url: event.actor.url.replace('/api/v3/users', ''),
      actor_avatar_url: event.actor.avatar_url,
      target: event.repo.name.indexOf('Blueprints') === 0 ? 'blueprint ' + event.repo.name.substr(11) : event.repo.name,
      target_url: event.repo.url.replace('/api/v3/repos', ''),
      data: event
      };
    if ('payload' in event) {
      if ('pull_request' in event.payload) {
        parsed.action = 'pull request ' + event.payload.pull_request.number;
        parsed.action_url = event.payload.pull_request.html_url;
      } else if ('commits' in event.payload) {
        parsed.action = event.payload.commits[0].message;
        parsed.action_url = event.payload.commits[0].url.replace('/api/v3/repos', '').replace('/commits/', '/commit/');
      }
      parsed.verb = event.payload.action;
    }
    var actionArray = event.type.match(/[A-Z][a-z]+/g).slice(0,-1);
    parsed.verb = parsed.verb || actionArray[0].toLowerCase() + 'ed';
    parsed.subject_type = actionArray.slice(1).join(' ').toLowerCase();
    parsed.article = 'on';
    switch(event.type)
    {
    case 'IssueCommentEvent':
      parsed.verb = 'issued';
      break;
    case 'CreateEvent':
      parsed.verb = 'created';
      parsed.article = '';
      break;
    case 'PullRequestEvent':
      parsed.subject_type = '';
      break;
    case 'PushEvent':
      parsed.article = 'to';
      break;
    case 'ForkEvent':
      parsed.article = '';
      break;
    default:
    }
    return parsed;
  };

  $scope.load = function() {
    var path = (checkmate_server_base || '') + '/githubproxy/api/v3/orgs/Blueprints/events';
    $http({method: 'GET', url: path, headers: {'X-Target-Url': 'https://github.rackspace.com', 'accept': 'application/json'}}).
      success(function(data, status, headers, config) {
        items.clear();
        items.receive(data, $scope.parse_event);
        $scope.count = items.count;
        $scope.items = items.all;
      }).
      error(function(data, status, headers, config) {
        var response = {data: data, status: status};
        //$scope.show_error(response);
      });
  };
  $scope.load();
}

function TestController($scope, $location, $routeParams, $resource, $http, items, navbar, settings, workflow) {
  $scope.prices = {
    single: {
      blueprint: 'https://github.rackspace.com/Blueprints/wordpress-single.git',
      core_price: '87.60',
      managed_price: '275.20'
    },
    double_dbaas: {
      blueprint: 'https://github.rackspace.com/Blueprints/wordpress-single-clouddb.git',
      core_price: '240.90',
      managed_price: '428.50',
      db_spec: '2 Gb Cloud Database'
    },
    double_mysql: {
      blueprint: 'https://github.rackspace.com/Blueprints/wordpress-single-db.git',
      core_price: '262.80',
      managed_price: '538.00',
      db_spec: '4 Gb Database Server'
    },
    multi_dbaas: {
      blueprint: 'https://github.rackspace.com/Blueprints/wordpress-clouddb.git',
      core_price: '478.15',
      managed_price: '694.95',
      db_spec: '4 Gb Cloud Database'
    },
    multi_mysql: {
      blueprint: 'https://github.rackspace.com/Blueprints/wordpress.git',
      core_price: '536.55',
      managed_price: '811.75',
      db_spec: '8 Gb Database Server'
    },
    double: {},
    multi: {}
  };

  $scope.service_level = $scope.is_managed_account() ? 'managed' : 'core';
  $scope.database_type = 'dbaas';

  $scope.updatePricing = function() {
    $scope.prices.single.price = $scope.prices.single[$scope.service_level + '_price'];
    $scope.prices.double.price = $scope.prices['double_' + $scope.database_type][$scope.service_level + '_price'];
    $scope.prices.multi.price = $scope.prices['multi_' + $scope.database_type][$scope.service_level + '_price'];
    $scope.prices.double.db_spec = $scope.prices['double_' + $scope.database_type].db_spec;
    $scope.prices.multi.db_spec = $scope.prices['multi_' + $scope.database_type].db_spec;
  };

  $scope.updatePricing();
}

//Workflow controllers
function WorkflowListController($scope, $location, $resource, workflow, items, navbar, scroll) {
  //Model: UI
  $scope.showItemsBar = true;
  $scope.showStatus = true;
  $scope.name = "Workflows";
  navbar.highlight("workflows");

  //Model: data
  $scope.count = 0;
  items.all = [];
  $scope.items = items.all;  // bind only to shrunken array

  $scope.selectedObject = function() {
    if (items.selected)
      return items.data[items.selected.id];
    return null;
  };

  $scope.selectItem = function(index) {
    items.selectItem(index);
    $scope.selected = items.selected;

    // Prepare tasks
    var wf = items.data[items.selected.id];
    $scope.task_specs = wf.wf_spec.task_specs;
    $scope.tasks = workflow.flattenTasks({}, wf.task_tree);
    $scope.jit = workflow.jitTasks($scope.tasks);

    // Render tasks
    workflow.renderWorkflow('#content', '#task', $scope.jit, $scope);
    prettyPrint();
  };

  $scope.selected = items.selected;

  $scope.refresh = function() {
  };

  $scope.handleSpace = function() {
  };

  $scope.load = function() {
    console.log("Starting load");
    this.klass = $resource((checkmate_server_base || '') + '/:tenantId/workflows/.json');
    this.klass.get({tenantId: $scope.auth.tenantId}, function(list, getResponseHeaders){
      console.log("Load returned");
      items.receive(list, function(item, key) {
        return {id: key, name: item.wf_spec.name, tenantId: item.tenantId};});
      $scope.count = items.count;
      $scope.items = items.all;
      console.log("Done loading");
    });
  };

  //Setup
  $scope.$watch('items.selectedIdx', function(newVal, oldVal, scope) {
    if (newVal !== null) scroll.toCurrent();
  });

  $scope.load();
}

function WorkflowController($scope, $resource, $http, $routeParams, $location, $window, workflow, items, scroll) {
  //Scope variables
  $scope.showStatus = true;
  $scope.showHeader = true;
  $scope.showSearch = true;
  $scope.showControls = true;
  $scope.taskStates = {
    future: 0,
    likely: 0,
    maybe: 0,
    waiting: 0,
    ready: 0,
    cancelled: 0,
    completed: 0,
    triggered: 0
  };

  $scope.load = function() {
    this.klass = $resource((checkmate_server_base || '') + '/:tenantId/workflows/:id.json');
    this.klass.get($routeParams,
                   function(object, getResponseHeaders){
      $scope.data = object;
      items.tasks = workflow.flattenTasks({}, object.task_tree);
      items.all = workflow.parseTasks(items.tasks, object.wf_spec.task_specs);
      $scope.count = items.all.length;
      workflow.calculateStatistics($scope, items.all);
      if ($location.path().split('/').slice(-1)[0] == 'status') {
        if ($scope.taskStates.completed < $scope.count) {
          setTimeout($scope.load, 2000);
        } else {
          var d = $resource((checkmate_server_base || '') + '/:tenantId/deployments/:id.json?with_secrets');
          d.get($routeParams, function(object, getResponseHeaders){
            $scope.output = {};
            //Get load balancer IP
            try {
              var lb = _.find(object.resources, function(r, k) { return r.type == 'load-balancer';});
              if ('instance' in lb) {
                $scope.output.vip = lb.instance.public_ip;
              }
            }
            catch (error) {
              console.log(error);
            }

            var domain = null;
            //Find domain in inputs
            try {
              domain = object.inputs.blueprint.domain;
              $scope.output.domain = domain;
            }
            catch (error) {
              console.log(error);
            }
            //If no domain, use load-balancer VIP
            if (domain === null) {
              domain = $scope.output.vip;
            }
            //Find path in inputs
            var path = "/";
            try {
              path = object.inputs.blueprint.path;
            }
            catch (error) {
              console.log(error);
            }
            if (domain !== undefined && path !== undefined)
              $scope.output.path = "http://" + domain + path;

            //Get user name/password
            try {
              var user = _.find(object.resources, function(r, k) { return r.type == 'user';});
              if ('instance' in user) {
                $scope.output.username = user.instance.name;
                $scope.output.password = user.instance.password;
              }
            }
            catch (error) {
              console.log(error);
            }

            //Get the private key
            try {
              var keypair = _.find(object.resources, function(r, k) { return r.type == 'key-pair';});
              if ('instance' in keypair) {
                $scope.output.private_key = keypair.instance.private_key;
              }
            }
            catch (error) {
              console.log(error);
            }

            //Copy resources into output as array (angular filters prefer arrays)
            $scope.output.resources = _.toArray(object.resources);
            //Get master server
            $scope.output.master_server = _.find($scope.output.resources, function(resource) {
                return (resource.component == 'linux_instance' && resource.service == 'master');
            });

            //Copy all data to all_data for clipboard use
            var all_data = [];
            all_data.push('From: ' + $location.absUrl());
            all_data.push('Wordpress URL: ' + $scope.output.path);
            all_data.push('Wordpress IP: ' +  $scope.output.vip);
            all_data.push('Servers: ');
            _.each($scope.output.resources, function(resource) {
                if (resource.component == 'linux_instance') {
                    all_data.push('  ' + resource.service + ' server: ' + resource['dns-name']);
                    if (resource.instance.public_ip === undefined) {
                        for (var nindex in resource.instance.interfaces.host.networks) {
                            var network = resource.instance.interfaces.host.networks[nindex]
                            if (network.name == 'public_net') {
                                for (var cindex in network.connections) {
                                    var connection = network.connections[cindex]
                                    if (connection.type == 'ipv4') {
                                        resource.instance.public_ip = connection.value;
                                        break;
                                    }
                                }
                                break;
                            }
                        }
                    }
                    all_data.push('    IP:      ' + resource.instance.public_ip);
                    all_data.push('    Role:    ' + resource.service);
                    all_data.push('    root pw: ' + resource.instance.password);
                }
            });
            all_data.push('Databases: ');
            _.each($scope.output.resources, function(resource) {
                if (resource.type == 'database') {
                    all_data.push('  ' + resource.service + ' database: ' + resource['dns-name']);
                    try {
                      all_data.push('    Host:       ' + resource.instance.interfaces.mysql.host);
                      all_data.push('    Username:   ' + resource.instance.interfaces.mysql.username);
                      all_data.push('    Password:   ' + resource.instance.interfaces.mysql.password);
                      all_data.push('    DB Name:    ' + resource.instance.interfaces.mysql.database_name);
                      //all_data.push('    Admin Link: https://' + $scope.output.master_server.instance.public_ip + '/database-admin');
                    } catch(err) {
                      // Do nothing - probably a MySQL on VMs build
                    }
                }
            });
            all_data.push('Load balancers: ');
            _.each($scope.output.resources, function(resource) {
                if (resource.type == 'load-balancer') {
                    all_data.push('  ' + resource.service + ' load-balancer: ' + resource['dns-name']);
                    all_data.push('    Public VIP:       ' + resource.instance.public_ip);
                }
            });
            all_data.push('Applications: ');
            if ($scope.output.username == undefined) {
                _.each($scope.output.resources, function(resource) {
                    if (resource.type == 'application' && resource.instance !== undefined) {
                        _.each(resource.instance, function(instance) {
                            if (instance.admin_user !== undefined) {
                                $scope.output.username = instance.admin_user;
                            }
                            if (instance.admin_password !== undefined) {
                                $scope.output.password = instance.admin_password;
                            }
                        });
                    }
                });
            }

            all_data.push('User:     ' + $scope.output.username);
            all_data.push('Password: ' + $scope.output.password);
            all_data.push('Priv Key: ' + $scope.output.private_key);
            $scope.all_data = all_data.join('\n');

          }, function(error) {
            console.log("Error " + error.data + "(" + error.status + ") loading deployment.");
            $scope.$root.error = {data: error.data, status: error.status, title: "Error loading deployment",
                    message: "There was an error loading your deployment:"};
            $('#modalError').modal('show');
          });
        }
      } else if ($location.hash().length > 1) {
        $scope.selectSpec($location.hash());
        $('#spec_list').css('top', $('.summaryHeader').outerHeight()); // Not sure if this is the right place for this. -Chris.Burrell (chri5089)
      } else
        $scope.selectSpec($scope.current_spec_index || Object.keys(object.wf_spec.task_specs)[0]);
      //$scope.play();
    }, function(response) {
        console.log("Error loading workflow.", response);
        var error = response.data.error;
        var info = {data: error,
                    status: response.status,
                    title: "Error Loading Workflow",
                    message: "There was an error loading your data:"};
        if ('description' in error)
            info.message = error.description;
        $scope.$root.error = info;
      $('#modalError').modal('show');
    });
  };

  //Parse loaded workflow
  $scope.parse = function(object) {
      $scope.data = object;
      if (typeof object == 'object' && 'task_tree' in object) {
        items.tasks = workflow.flattenTasks({}, object.task_tree);
        items.all = workflow.parseTasks(items.tasks, object.wf_spec.task_specs);
        $scope.count = items.all.length;
        workflow.calculateStatistics($scope, items.all);
      } else {
        items.clear();
      }
  };

  $scope.percentComplete = function() {
    return (($scope.totalTime - $scope.timeRemaining) / $scope.totalTime) * 100;
  };

  $scope.selectSpec = function(spec_id) {
    $scope.current_spec_index = spec_id;
    $scope.current_spec = $scope.data.wf_spec.task_specs[$scope.current_spec_index];
    $scope.current_spec_json = JSON.stringify($scope.current_spec, null, 2);

    var alltasks = items.tasks;
    var tasks = _.filter(alltasks, function(task, key) {
        return task.task_spec == spec_id;
      });
    $scope.current_spec_tasks = tasks;
    tasks = $scope.spec_tasks(spec_id);
    console.log(tasks, $scope.current_task, typeof task);
    if (tasks && !(_.include(tasks, $scope.current_task))) {
      $scope.selectTask(tasks[0].id);
      $scope.toCurrent();
    }
    if ($location.hash() != spec_id)
        $location.hash(spec_id);
  };

  $scope.toCurrent = function() {
    // Need the setTimeout to prevent race condition with item being selected.
    window.setTimeout(function() {
        var curScrollPos = $('#spec_list').scrollTop();
            var item = $('.summary.active').offset();
            if (item !== null) {
                  var itemTop = item.top - 250;
                  $('.summaries').animate({'scrollTop': curScrollPos + itemTop}, 200);
            }
    }, 0);
  };

  $scope.state_class = function(task) {
    return workflow.classify(task);
  };

  $scope.state_name = function(task) {
    return workflow.state_name(task);
  };

  $scope.save_spec = function() {
    var editor = _.find($('.CodeMirror'), function(c) {
      return c.CodeMirror.getTextArea().id == 'spec_source';
      });

    if ($scope.auth.loggedIn) {
      var klass = $resource((checkmate_server_base || '') + '/:tenantId/workflows/:id/specs/' + $scope.current_spec_index);
      var thang = new klass(JSON.parse(editor.CodeMirror.getValue()));
      thang.$save($routeParams, function(returned, getHeaders){
          // Update model
          for (var attr in returned) {
            if (returned.hasOwnProperty(attr))
              $scope.current_spec[attr] = returned[attr];
          }
          $scope.notify('Saved');
        }, function(error) {
          $scope.$root.error = {data: error.data, status: error.status, title: "Error Saving",
                  message: "There was an error saving your JSON:"};
          $('#modalError').modal('show');
        });
    } else {
      $scope.loginPrompt(this, function() {console.log("Failed");}); //TODO: implement a callback
    }
  };

  $scope.selectTask = function(task_id) {
    $scope.current_task_index = task_id;
    var alltasks = workflow.flattenTasks({}, $scope.data.task_tree);
    $scope.current_task = _.find(alltasks, function(task){ return task.id == task_id;});
    // Make copy with no children
    var copy = {};
    var obj = $scope.current_task;
    for (var attr in obj) {
      if (['children', "$$hashKey"].indexOf(attr) == -1 && obj.hasOwnProperty(attr))
        copy[attr] = obj[attr];
    }
    try {
        $scope.$apply($scope.current_task_json = JSON.stringify(copy, null, 2));
    } catch(err) {}
    // Refresh CodeMirror since it might have been hidden
    _.each($('.CodeMirror'), function(inst) { inst.CodeMirror.refresh(); });
  };

  $scope.save_task = function() {
    var editor = _.find($('.CodeMirror'), function(c) {
      return c.CodeMirror.getTextArea().id == 'task_source';
      });

    if ($scope.auth.loggedIn) {
      var klass = $resource((checkmate_server_base || '') + '/:tenantId/workflows/:id/tasks/' + $scope.current_task_index);
      var thang = new klass(JSON.parse(editor.CodeMirror.getValue()));
      thang.$save($routeParams, function(returned, getHeaders){
          // Update model
          for (var attr in returned) {
            if (['workflow_id', "tenantId"].indexOf(attr) == -1 && returned.hasOwnProperty(attr))
              $scope.current_task[attr] = returned[attr];
          }
          $scope.notify('Saved');
        }, function(error) {
          $scope.$root.error = {data: error.data, status: error.status, title: "Error Saving",
                  message: "There was an error saving your JSON:"};
          $('#modalError').modal('show');
        });
    } else {
      $scope.loginPrompt(this); //TODO: implement a callback
    }
  };

  //Return all tasks for a spec
  $scope.spec_tasks = function(spec_id) {
    return _.filter(items.tasks || [], function(task, key) {
        return task.task_spec == spec_id;
      });
  };

  //Return count of tasks for a spec
  $scope.task_count = function(spec_id) {
    return $scope.spec_tasks(spec_id).length;
  };

  //Return net status for a spec
  $scope.spec_status = function(spec_id) {
    var tasks = $scope.spec_tasks(spec_id);
    var status = 64;
    _.each(tasks, function(task){
      if (task.state < status)
        status = task.state;
        if ('internal_attributes' in task && 'task_state' in task.internal_attributes && task.internal_attributes.task_state.state == 'FAILURE' && task.state != 64)
          status = -1;
    });
    return status;
  };

  $scope.workflow_action = function(workflow_id, action) {
    if ($scope.auth.loggedIn) {
      console.log("Executing '" + action + " on workflow " + workflow_id);
      $http({method: 'GET', url: $location.path() + '/+' + action}).
        success(function(data, status, headers, config) {
          $scope.notify("Command '" + action + "' workflow executed");
          // this callback will be called asynchronously
          // when the response is available
          $scope.load();
        });
    } else {
      $scope.loginPrompt(); //TODO: implement a callback
    }
  };

  $scope.task_action = function(task_id, action) {
    if ($scope.auth.loggedIn) {
      console.log("Executing '" + action + " on task " + task_id);
      $http({method: 'POST', url: $location.path() + '/tasks/' + task_id + '/+' + action}).
        success(function(data, status, headers, config) {
          $scope.notify("Command '" + action + "' task executed");
          // this callback will be called asynchronously
          // when the response is available
          $scope.load();
        });
    } else {
      $scope.loginPrompt(); //TODO: implement a callback
    }
  };

  $scope.execute_task = function() {
    return $scope.task_action($scope.current_task.id, 'execute');
  };

  $scope.reset_task = function() {
    return $scope.task_action($scope.current_task.id, 'reset');
  };

  $scope.resubmit_task = function() {
    return $scope.task_action($scope.current_task.id, 'resubmit');
  };

  $scope.was_server_created = function() {
    if (typeof $scope.current_task != 'undefined' && ($scope.current_task.task_spec.indexOf("Create Server") === 0 || $scope.current_task.task_spec.indexOf("Wait for Server") === 0) &&
        $scope.resource($scope.current_task) !== null)
      return true;
    return false;
  };

  $scope.was_database_created = function() {
    if (typeof $scope.current_task != 'undefined' && ($scope.current_task.task_spec.indexOf("Create Database") === 0 || $scope.current_task.task_spec.indexOf("Add DB User") === 0) &&
        $scope.resource($scope.current_task) !== null)
      return true;
    return false;
  };

  $scope.was_loadbalancer_created = function() {
    if (typeof $scope.current_task != 'undefined' && ($scope.current_task.task_spec.indexOf("Load") != -1 || $scope.current_task.task_spec.indexOf("alancer") != -1) &&
        $scope.resource($scope.current_task) !== null)
      return true;
    return false;
  };

  $scope.CloudControlURL = function(region) {
    if (region == 'LON')
      return "https://lon.cloudcontrol.rackspacecloud.com";
    return "https://us.cloudcontrol.rackspacecloud.com"
  };

  $scope.resource = function(task) {
    if (typeof task == 'undefined')
      return null;
    try {
      var res = _.find(task.attributes, function(obj, attr) {
        if (attr.indexOf("instance:") === 0)
          return true;
        return false;
      });

      if (typeof res != "undefined")
        return res;
      return null;
    } catch(err) {
      console.log("Error in WorkflowController.resource: " + err);
    }
  };

  //Init
  if (!$scope.auth.loggedIn) {
    $scope.loginPrompt($scope.load);
  } else if ($location.path().split('/').slice(-1)[0] == '+preview') {
    if (typeof workflow.preview == 'object') {
      $scope.parse(workflow.preview['workflow']);
    } else {
      $scope.parse();
    }
  } else
    $scope.load();

  //Not real code. Just testing stuff
  $scope.showConnections = function(task_div) {
    jsPlumb.Defaults.Container = "entry";

    var selectedTask = _.find($scope.tasks, function(task) {
      if (task.id === parseInt(task_div.attr('id'), 10))
        return task;
      return null;
    });

    jsPlumb.addEndpoint(selectedTask.id);
    _.each(selectedTask.children, function(child) {
      jsPlumb.addEndpoint(child.id);

      jsPlumb.connect({
        source: selectedTask.id,
        target: child.id
      });
    });
  };

  $scope.play = function() {
    var w = 960,
    h = 500;

    var vis = d3.select(".entries").append("svg:svg")
        .attr("width", w)
        .attr("height", h);
    var links = _.each($scope.data.wf_spec.task_specs, function(t, k) {return {"source": k, "target": "Root"};});
    var nodes = _.each($scope.data.wf_spec.task_specs, function(t, k) {return t;});

    var force = self.force = d3.layout.force()
        .nodes(nodes)
        .links(links)
        .gravity(0.05)
        .distance(100)
        .charge(-100)
        .size([w, h])
        .start();

    var link = vis.selectAll("line.link")
        .data(links)
        .enter().append("svg:line")
        .attr("class", "link")
        .attr("x1", function(d) { return d.source.x; })
        .attr("y1", function(d) { return d.source.y; })
        .attr("x2", function(d) { return d.target.x; })
        .attr("y2", function(d) { return d.target.y; });

    var node_drag = d3.behavior.drag()
        .on("dragstart", dragstart)
        .on("drag", dragmove)
        .on("dragend", dragend);

    function dragstart(d, i) {
        force.stop(); // stops the force auto positioning before you start dragging
    }

    function dragmove(d, i) {
        d.px += d3.event.dx;
        d.py += d3.event.dy;
        d.x += d3.event.dx;
        d.y += d3.event.dy;
        tick(); // this is the key to make it work together with updating both px,py,x,y on d !
    }

    function dragend(d, i) {
        d.fixed = true; // of course set the node to fixed so the force doesn't include the node in its auto positioning stuff
        tick();
        force.resume();
    }


    var node = vis.selectAll("g.node")
        .data(json.nodes)
      .enter().append("svg:g")
        .attr("class", "node")
        .call(node_drag);

    node.append("svg:image")
        .attr("class", "circle")
        .attr("xlink:href", "https://d3nwyuy0nl342s.cloudfront.net/images/icons/public.png")
        .attr("x", "-8px")
        .attr("y", "-8px")
        .attr("width", "16px")
        .attr("height", "16px");

    node.append("svg:text")
        .attr("class", "nodetext")
        .attr("dx", 12)
        .attr("dy", ".35em")
        .text(function(d) { return d.name; });

    force.on("tick", tick);

    function tick() {
      link.attr("x1", function(d) { return d.source.x; })
          .attr("y1", function(d) { return d.source.y; })
          .attr("x2", function(d) { return d.target.x; })
          .attr("y2", function(d) { return d.target.y; });

      node.attr("transform", function(d) { return "translate(" + d.x + "," + d.y + ")"; });
    }

  };

  // Old code we might reuse
  $scope.showConnections = function(task_div) {
    jsPlumb.Defaults.Container = "task_container";

    var selectedTask = _.find($scope.tasks, function(task) {
      if (task.id === parseInt(task_div.attr('id'), 10))
        return task;
      return null;
    });
    var source = $('#' + selectedTask.id);
    _.each(selectedTask.children, function(child) {
      var target = $('#' + child.id);
      if (target.length != 1) {
        console.log("Error finding child " + child.id + " there were " + target.length + " matches.");
      } else {
        jsPlumb.connect({
          source: source,
          target: target
        });
      }
     });
  };
}

//Blueprint controllers
function BlueprintListController($scope, $location, $routeParams, $resource, items, navbar, settings, workflow,
                                 blueprints, initial_blueprint, environments, initial_environment) {
  //Model: UI
  $scope.showSummaries = true;
  $scope.showStatus = true;
  $scope.name = 'Blueprints';
  navbar.highlight("blueprints");

  $scope.environments = environments;
  $scope.environment = (typeof environments == "object" && Object.keys(environments).length >= 0) ? environments[initial_environment || Object.keys(environments)[0]] : null;
  items.receive(blueprints, function(item, key) {
    return {key: key, id: item.id, name: item.name, description: item.description, selected: false};});
  $scope.count = items.count;
  $scope.items = items.all;

  $scope.selectItem = function(index) {
    items.selectItem(index);
    $scope.selected = items.selected;
  };

  for (var i=0;i<items.count;i++) {
    if (items.all[i].key == initial_blueprint) {
      console.log('Found and selecting initial blueprint');
      items.selectItem(i);
      $scope.selected = items.selected;
      break;
    }
  }
  if (typeof items.selected != 'object' && $scope.count > 0) {
    console.log('Selecting first blueprint');
    items.selectItem(index);
    $scope.selected = items.selected;
  }

  //Inherit from Deployment Initializer
  DeploymentNewController($scope, $location, $routeParams, $resource, settings, workflow, $scope.selected, $scope.environment);

  //Wire Blueprints to Deployment
  $scope.$watch('selected', function(newVal, oldVal, scope) {
    if (typeof newVal == 'object') {
       $scope.setBlueprint(blueprints[newVal.key]);
    }
  });
}

function BlueprintRemoteListController($scope, $location, $routeParams, $resource, $http, items, navbar, settings, workflow, github) {
  //Inherit from Blueprint List Controller
  BlueprintListController($scope, $location, $routeParams, $resource, items, navbar, settings, workflow, {}, null, {}, null);
  //Model: UI
  $scope.loading_remote_blueprints = false;

  $scope.default_branch = 'master';
  $scope.remote = {};
  $scope.remote.url = null;
  $scope.remote.server = null;
  $scope.remote.owner = null;
  $scope.remote.org = null;
  $scope.remote.user = null;
  $scope.remote.repo = null;
  $scope.remote.branch = null;

  $scope.parse_org_url = function(url) {
    console.log('parse_org_url', url);
    $scope.loading_remote_blueprints = true;
    $scope.remote = github.parse_org_url(url, $scope.load);
  };

  //Handle results of loading repositories
  $scope.receive_blueprints = function(data) {
    items.clear();
    items.receive(data, function(item, key) {
      return {key: item.id, id: item.html_url, name: item.name, description: item.description, git_url: item.git_url, selected: false};});
    $scope.count = items.count;
    $scope.items = items.all;
    $scope.loading_remote_blueprints = false;
  };

  $scope.load = function() {
    console.log("Starting load", $scope.remote);
    $scope.loading_remote_blueprints = true;
    github.get_repos($scope.remote, $scope.receive_blueprints, function(data) {
      $scope.loading_remote_blueprints = false;
      $scope.show_error(data);
    });
  };

  $scope.reload_blueprints = function() {
    console.log('reload_blueprints', $scope.remote);
    $scope.items = [];
    items.clear();
    $scope.parse_org_url($scope.remote.url);
  };

  $scope.receive_branches = function(data) {
    console.log("BRANCHES", data);
    $scope.branches = data;
    if (data.length >= 1) {
      var select = _.find(data, function(branch) {return branch.name == $scope.default_branch;});
      $scope.remote.branch = select || data[0];
      $scope.loadBlueprint();
    } else
      $scope.remote.branch = null;
  };

  $scope.get_branches = function() {
    console.log('get_branches');
    github.get_branches($scope.remote, $scope.receive_branches, function(response) {
      $scope.branches = [];
      $scope.remote.branch = null;
    });
  };

  $scope.receive_blueprint = function(data) {
    if ('environment' in data) {
      if (!('name' in data.environment))
        data.environment.name = "- not named -";
      if (!('id' in data.environment))
        data.environment.id = "included";
      var env_name = data.environment.name;
      $scope.environments = {env_name: data.environment};
      $scope.environment = data.environment;
    } else {
      //TODO: create from catalog
      $scope.environments = {};
      $scope.environment = null;
    }

    if ('blueprint' in data) {
      $scope.blueprint = data.blueprint;
    } else {
      $scope.blueprint = null;
    }
    $scope.updateSettings();
  };

  $scope.loadBlueprint = function() {
    console.log('loadBlueprint', $scope.remote);
    github.get_blueprint($scope.remote, $scope.auth.username, $scope.receive_blueprint, function(data) {
      if (typeof data == 'string') {
        $scope.notify(data);
      } else {
        $scope.show_error(data);
      }
    });
  };

  $scope.$watch('selected', function(newVal, oldVal, scope) {
    if (typeof newVal == 'object') {
      $scope.remote.repo = newVal;
      $scope.get_branches();  //calls loadBlueprint()
    }
  });
}

//Deployment controllers
function DeploymentListController($scope, $location, $http, $resource, scroll, items, navbar) {
  //Model: UI
  $scope.showItemsBar = true;
  $scope.showStatus = true;
  $scope.name = "Deployments";
  navbar.highlight("deployments");

  //Model: data
  $scope.count = 0;
  items.all = [];
  $scope.items = items.all;  // bind only to shrunken array

  $scope.selectedObject = function() {
    if (items.selected)
      return items.data[items.selected.id];
    return null;
  };

  $scope.selectItem = function(index) {
    items.selectItem(index);
    $scope.selected = items.selected;
  };

  $scope.selected = items.selected;

  $scope.refresh = function() {
  };

  $scope.handleSpace = function() {
  };

  $scope.load = function() {
    console.log("Starting load");
    this.klass = $resource((checkmate_server_base || '') + '/:tenantId/deployments/.json');
    this.klass.get({tenantId: $scope.auth.tenantId}, function(list, getResponseHeaders){
      console.log("Load returned");
      items.all = [];
      items.receive(list, function(item) {
        return {id: item.id, name: item.name, created: item.created, tenantId: item.tenantId,
                blueprint: item.blueprint, environment: item.environment,
                status: item.status};});
      $scope.count = items.count;
      $scope.items = items.all;
      console.log("Done loading");
    });
  };

  //Setup
  $scope.$watch('items.selectedIdx', function(newVal, oldVal, scope) {
    if (newVal !== null) scroll.toCurrent();
  });

  $scope.load();
}

//Hard-coded for Managed Cloud Wordpress
function DeploymentManagedCloudController($scope, $location, $routeParams, $resource, $http, items, navbar, settings, workflow) {

  $scope.loadRemoteBlueprint = function(blueprint_name) {
    $http({method: 'GET', url: (checkmate_server_base || '') + '/githubproxy/api/v3/repos/Blueprints/' + blueprint_name + '/git/trees/master',
        headers: {'X-Target-Url': 'https://github.rackspace.com/', 'accept': 'application/json'}}).
    success(function(data, status, headers, config) {
      var checkmate_yaml_file = _.find(data.tree, function(file) {return file.path == "checkmate.yaml";});
      if (checkmate_yaml_file === undefined) {
        $scope.notify("No 'checkmate.yaml' found in the repository '" + $scope.selected.name + "'");
      } else {
        $http({method: 'GET', url: (checkmate_server_base || '') + '/githubproxy/api/v3/repos/Blueprints/' + blueprint_name + '/git/blobs/' + checkmate_yaml_file.sha,
            headers: {'X-Target-Url': 'https://github.rackspace.com/', 'Accept': 'application/vnd.github.v3.raw'}}).
        success(function(data, status, headers, config) {
          var checkmate_yaml = {};
          try {
            checkmate_yaml = YAML.parse(data);
          } catch(err) {
            if (err.name == "YamlParseException")
              $scope.notify("YAML syntax error in line " + err.parsedLine + ". '" + err.snippet + "' caused error '" + err.message + "'");
          }
          if ('blueprint' in checkmate_yaml) {
            if ($scope.auth.loggedIn === true) {
              checkmate_yaml.blueprint.options.region['default'] = $scope.auth.catalog.access.user['RAX-AUTH:defaultRegion'] || $scope.auth.catalog.access.regions[0];
              checkmate_yaml.blueprint.options.region.choice = $scope.auth.catalog.access.regions;
            }
            WPBP[blueprint_name] = checkmate_yaml.blueprint;
            var new_blueprints = {};
            new_blueprints[blueprint_name] = checkmate_yaml.blueprint;
            items.receive(new_blueprints, function(item, key) {
              return {key: key, id: item.id, name: item.name, description: item.description, selected: false};});
            $scope.count = items.count;
            $scope.items = items.all;
          }
        }).
        error(function(data, status, headers, config) {
          $scope.notify('Unable to load latest version of ' + blueprint_name + ' from github');
        });
      }
    }).
    error(function(data, status, headers, config) {
      $scope.notify('Unable to find latest version of ' + blueprint_name + ' from github');
    });
  };

  //Default Environments
  var ENVIRONMENTS = {
      "legacy": {
          "description": "This environment uses legacy cloud servers.",
          "name": "Legacy Cloud Servers",
          "providers": {
              "legacy": {},
              "chef-local": {
                  "vendor": "opscode",
                  "provides": [
                      {
                          "application": "http"
                      },
                      {
                          "database": "mysql"
                      },
                      {
                          "compute": "mysql"
                      }
                  ]
              },
              "common": {
                  "vendor": "rackspace"
              },
              "load-balancer": {}
          }
      },
      "next-gen": {
          "description": "This environment uses next-gen cloud servers.",
          "name": "Next-Gen Open Cloud",
          "providers": {
              "nova": {},
              "chef-local": {
                  "vendor": "opscode",
                  "provides": [
                      {
                          "application": "http"
                      },
                      {
                          "database": "mysql"
                      },
                      {
                          "compute": "mysql"
                      }
                  ]
              },
              "common": {
                  "vendor": "rackspace"
              },
              "load-balancer": {}
          }
      }
  };

  //Initial Wordpress Templates
  var WPBP = {};
  //Load the two tested versions stored in Rook
  WPBP.DBaaS = YAML.parse(dbaasBlueprint.innerHTML).blueprint;
  WPBP.MySQL = YAML.parse(mysqlBlueprint.innerHTML).blueprint;

  $scope.setAllBlueprintRegions = function() {
    _.each(WPBP, function(value, key) {
      value.options.region['default'] = $scope.auth.catalog.access.user['RAX-AUTH:defaultRegion'] || $scope.auth.catalog.access.regions[0];
      value.options.region.choice = $scope.auth.catalog.access.regions;
    });
  };

  if ($scope.auth.loggedIn === true) {
      $scope.setAllBlueprintRegions();
  }

  //Show list of supported Managed Cloud blueprints
  items.clear();
  //$scope.blueprints = WPBP;
  BlueprintListController($scope, $location, $routeParams, $resource, items, navbar, settings, workflow,
                          WPBP, 'MySQL', ENVIRONMENTS, 'next-gen');
  //$scope.showSummaries = false;

  $scope.updateDatabaseProvider = function() {
    if ($scope.blueprint.id == WPBP.MySQL.id) {
        //Remove DBaaS Provider
        if ('database' in $scope.environment.providers)
            delete $scope.environment.providers.database;
        //Add database support to chef provider
        $scope.environment.providers['chef-local'].provides[1] = {database: "mysql"};
    } else if ($scope.blueprint.id == WPBP.DBaaS.id) {
        //Add DBaaS Provider
        $scope.environment.providers.database = {};
        //Remove database support from chef-local
        if ($scope.environment.providers['chef-local'].provides.length > 1)
            $scope.environment.providers['chef-local'].provides.pop(1);
        if ($scope.environment.providers['chef-local'].provides.length > 1)
            $scope.environment.providers['chef-local'].provides.pop(1);
    }
  };

  $scope.updateSettings();
  $scope.updateDatabaseProvider();

  //Wire Blueprints to Deployment
  $scope.$watch('blueprint', function(newVal, oldVal, scope) {
    if (typeof newVal == 'object') {
      $scope.updateDatabaseProvider();
    }
  });

  // Event Listeners
  $scope.$on('logIn', function(e) {
    $scope.setAllBlueprintRegions();
  });

  //Load the latest master from github
  $scope.loadRemoteBlueprint('wordpress');
  $scope.loadRemoteBlueprint('wordpress-clouddb');
}

//Select one remote blueprint
function DeploymentNewRemoteController($scope, $location, $routeParams, $resource, $http, items, navbar, settings, workflow, github) {

  var blueprint = $location.search().blueprint;
  var u = URI(blueprint);

  BlueprintRemoteListController($scope, $location, $routeParams, $resource, $http, items, navbar, settings, workflow, github);

  //Override it with a one repo load
  $scope.load = function() {
    console.log("Starting load", $scope.remote);
    $scope.loading_remote_blueprints = true;
    github.get_repo($scope.remote, $scope.remote.repo.name,
      function(data) {
        $scope.remote.repo = data;
        $scope.default_branch = u.fragment() || 'master';
        $scope.selected = $scope.remote.repo;
      },
      function(data) {
        $scope.loading_remote_blueprints = false;
        $scope.show_error(data);
      });
  };

  //Instead of parse_org_url
  $scope.loading_remote_blueprints = true;
  $scope.remote = github.parse_org_url(blueprint, $scope.load);

}

// Handles the option setting and deployment launching
function DeploymentNewController($scope, $location, $routeParams, $resource, settings, workflow, blueprint, environment) {
  $scope.environment = environment;
  $scope.settings = [];
  $scope.answers = {};
  $scope.domain_names = null;
  $scope.manual_site_address = null;
  $scope.show_site_address_controls = false;

  $scope.submitting = false; //Turned on while we are processing a deployment

  //Retrieve existing domains
  $scope.getDomains = function(){
    $scope.domain_names = [];
    if ($scope.auth.loggedIn){
      var tenant_id = $scope.auth.tenantId;
      url = '/:tenantId/providers/rackspace.dns/proxy/v1.0/'+tenant_id+'/domains.json';
      var Domains = $resource((checkmate_server_base || '') + url, {tenantId: $scope.auth.tenantId});
      var domains = Domains.query(function() {
        for(var i=0; i<domains.length; i++){
          $scope.domain_names.push(domains[i].name);
        }
       },
       function(response) {
          if (!('data' in response))
            response.data = {};
          response.data.description = "Error loading domain list";
        }
      );
    }
  };

  $scope.setBlueprint = function(blueprint) {
    $scope.blueprint = blueprint;
    $scope.updateSettings();
  };

  $scope.updateSettings = function() {
    $scope.settings = [];
    $scope.answers = {};

    if ($scope.blueprint) {
      $scope.settings = $scope.settings.concat(settings.getSettingsFromBlueprint($scope.blueprint));
    }

    if ($scope.environment) {
      $scope.settings = $scope.settings.concat(settings.getSettingsFromEnvironment($scope.environment));
      if ('legacy' in $scope.environment.providers) {
        if ($scope.settings && $scope.auth.loggedIn === true && 'RAX-AUTH:defaultRegion' in $scope.auth.catalog.access.user) {
            _.each($scope.settings, function(setting) {
                if (setting.id == 'region') {
                    setting['default'] = $scope.auth.catalog.access.user['RAX-AUTH:defaultRegion'];
                    setting.choice = [setting['default']];
                    setting.description = "Your legacy cloud servers region is '" + setting['default'] + "'. You can only deploy to this region";
                }
            });
        }
      }
    }

    _.each($scope.settings, function(setting) {
      if ('default' in setting) {
        $scope.answers[setting.id] = setting['default'];
      } else
        $scope.answers[setting.id] = null;
      if (setting.id == 'region' && $scope.auth.loggedIn === true)
        setting.choice = $scope.auth.catalog.access.regions;
    });
    $scope.show_site_address_controls = _.any($scope.settings, function(setting) {return ['domain', 'web_server_protocol'].indexOf(setting.id) > -1;});
    if (_.any($scope.settings, function(setting) {return setting.id == 'domain';}) && $scope.domain_names === null)
      $scope.getDomains();
  };

  $scope.OnAddressEditorShow = function() {
    site_address.value = calculated_site_address.innerText;
  };

  $scope.UpdateSiteAddress = function(new_address) {
    var parsed = URI.parse(new_address);
    if (!('hostname' in parsed)) {
        $('#site_address_error').text("Domain name or IP address missing");
        return;
    }
    if (!('protocol' in parsed)){
        $('#site_address_error').text("Protocol (http or https) is missing");
        return;
    }
    $('#site_address_error').text("");
    $scope.answers['web_server_protocol'] = parsed.protocol;
    $scope.answers['domain'] = parsed.hostname;
    $scope.answers['path'] = parsed.path || "/";
  };

  $scope.UpdateURL = function(scope, setting_id) {
    var new_address = scope.protocol + '://' + scope.domain + scope.path;
    var parsed = URI.parse(new_address);
    if (!('hostname' in parsed)) {
        $('#site_address_error').text("Domain name or IP address missing");
        return;
    }
    if (!('protocol' in parsed)){
        $('#site_address_error').text("Protocol (http or https) is missing");
        return;
    }
    $('#site_address_error').text("");
    $scope.answers[setting_id] = new_address;
  };

  $scope.UpdateParts = function(scope, setting_id) {
    try {
      var parsed = URI.parse($scope.answers[setting_id]);
      if (!('hostname' in parsed)) {
          $('#site_address_error').text("Domain name or IP address missing");
          return;
      }
      if (!('protocol' in parsed)){
          $('#site_address_error').text("Protocol (http or https) is missing");
          return;
      }
      scope.protocol = parsed.protocol;
      scope.domain = parsed.hostname;
      scope.path = parsed.path;
    } catch(err) {}
    $('#site_address_error').text("");
  };

  $scope.ShowCerts = function() {
    if ('web_server_protocol' in $scope.answers && $scope.answers['web_server_protocol'].indexOf('https') != -1)
      return true;
    if ('url' in $scope.answers && $scope.answers['url'].indexOf('https') != -1)
      return true;
    return false;
  };

  // Display settings using templates for each type
  $scope.renderSetting = function(setting) {
    var message;
    if (!setting) {
      message = "The requested setting is null";
      console.log(message);
      return "<em>" + message + "</em>";
    }
    if (!setting.type || !_.isString(setting.type)) {
      message = "The requested setting '" + setting.id + "' has no type or the type is not a string.";
      console.log(message);
      return "<em>" + message + "</em>";
    }
    var lowerType = setting.type.toLowerCase().trim();

    if (setting.label == "Domain") {
        setting.choice = $scope.domain_names;
    }

    if (lowerType == "select") {
      if ("choice" in setting) {
        if (!_.isString(setting.choice[0]))
          lowerType = lowerType + "-kv";
      }
    }
    var template = $('#setting-' + lowerType).html();
    if (template === null) {
      message = "No template for setting type '" + setting.type + "'.";
      console.log(message);
      return "<em>" + message + "</em>";
    }
      return (template || "").trim();
  };

  $scope.showSettings = function() {
    return ($scope.environment && $scope.blueprint);
  };

  $scope.submit = function(action) {
    if ($scope.submitting === true)
      return;
    $scope.submitting = true;
    var url = '/:tenantId/deployments';
    if ((action !== undefined) && action)
      url += '/' + action;
    var Deployment = $resource((checkmate_server_base || '') + url, {tenantId: $scope.auth.tenantId});
    var deployment = new Deployment({});
    deployment.blueprint = $scope.blueprint;
    deployment.environment = $scope.environment;
    deployment.inputs = {};
    deployment.inputs.blueprint = {};
    break_flag = false;

    // Have to fix some of the answers so they are in the right format, specifically the select
    // and checkboxes. This is lame and slow and I should figure out a better way to do this.
    _.each($scope.answers, function(element, key) {
      var setting = _.find($scope.settings, function(item) {
        if (item.id == key)
          return item;
        return null;
      });

      if (setting === undefined){
        console.log("WARNING: expected setting '" + key + "' is undefined");
        return;
      }

      //Check that all required fields are set
      if (setting.required === true) {
        if ($scope.answers[key] === null) {
          err_msg = "Required field "+key+" not set. Aborting deployment.";
          $scope.notify(err_msg);
          break_flag = true;
        }
      }

      if (setting.type === "boolean") {
        if ($scope.answers[key] === null) {
          deployment.inputs.blueprint[key] = false;
        } else {
          deployment.inputs.blueprint[key] = $scope.answers[key];
        }
      } else {
        deployment.inputs.blueprint[key] = $scope.answers[key];
      }
    });

    if (break_flag){
      $scope.submitting = false;
      return;
    }

    if ($scope.auth.loggedIn) {
        deployment.$save(function(returned, getHeaders){
        if (action == '+preview') {
            workflow.preview = returned;
            $location.path('/' + $scope.auth.tenantId + '/workflows/+preview');
        } else {
            var deploymentId = getHeaders('location').split('/')[3];
            console.log("Posted deployment", deploymentId);
            $location.path('/' + $scope.auth.tenantId + '/workflows/' + deploymentId + '/status');
        }
      }, function(error) {
        console.log("Error " + error.data + "(" + error.status + ") creating new deployment.");
        console.log(deployment);
        $scope.$root.error = {data: error.data, status: error.status, title: "Error Creating Deployment",
                message: "There was an error creating your deployment:"};
        $('#modalError').modal('show');
        $scope.submitting = false;
      });
    } else {
      $scope.submitting = false;
      $scope.loginPrompt(); //TODO: implement a callback
    }
  };

  $scope.simulate = function() {
    $scope.submit('simulate');
  };

  $scope.preview = function() {
    $scope.submit('+preview');
  };

  $scope.setBlueprint(blueprint);

  // Event Listeners
  $scope.OnLogIn = function(e) {
    $scope.getDomains();
    $scope.updateSettings();
  };
  $scope.$on('logIn', $scope.OnLogIn);

}

function DeploymentController($scope, $location, $resource, $routeParams) {
  //Model: UI
  $scope.showSummaries = true;
  $scope.showStatus = false;

  $scope.name = 'Deployment';
  $scope.data = {};
  $scope.data_json = "";

  $scope.refresh = function() {
  };

  $scope.handleSpace = function() {
  };

  $scope.load = function() {
    console.log("Starting load");
    this.klass = $resource((checkmate_server_base || '') + '/:tenantId/deployments/:id.json');
    this.klass.get($routeParams, function(data, getResponseHeaders){
      console.log("Load returned");
      $scope.data = data;
      $scope.data_json = JSON.stringify(data, null, 2);
      console.log("Done loading");
    });
  };

  $scope.save = function() {
    var editor = _.find($('.CodeMirror'), function(c) {
      return c.CodeMirror.getTextArea().id == 'source';
      });

    if ($scope.auth.loggedIn) {
      var klass = $resource((checkmate_server_base || '') + '/:tenantId/deployments/:id/.json', null, {'get': {method:'GET'}, 'save': {method:'PUT'}});
      var thang = new klass(JSON.parse(editor.CodeMirror.getValue()));
      thang.$save($routeParams, function(returned, getHeaders){
          // Update model
          $scope.data = returned;
          $scope.data_json = JSON.stringify(returned, null, 2);
          $scope.notify('Saved');
        }, function(error) {
          $scope.$root.error = {data: error.data, status: error.status, title: "Error Saving",
                  message: "There was an error saving your JSON:"};
          $('#modalError').modal('show');
        });
    } else {
      $scope.loginPrompt(this, function() {console.log("Failed");}); //TODO: implement a callback
    }
  };

  //Setup
  $scope.$watch('items.selectedIdx', function(newVal, oldVal, scope) {
    if (newVal !== null) scroll.toCurrent();
  });

  $scope.load();
}

//Provider controllers
function ProviderListController($scope, $location, $resource, items, scroll) {
  //Model: UI
  $scope.showSummaries = true;
  $scope.showStatus = false;

  $scope.name = 'Providers';
  $scope.count = 0;
  items.all = [];
  $scope.items = items.all;  // bind only to shrunken array

  $scope.refresh = function() {
  };

  $scope.handleSpace = function() {
  };

  $scope.load = function() {
    console.log("Starting load");
    this.klass = $resource((checkmate_server_base || '') + '/:tenantId/providers/.json');
    this.klass.get({tenantId: $scope.auth.tenantId}, function(list, getResponseHeaders){
      console.log("Load returned");
      items.receive(list, function(item, key) {
        return {id: key, name: item.name, vendor: item.vendor};});
      $scope.count = items.count;
      $scope.items = items.all;
      console.log("Done loading");
    });
  };

  //Setup
  $scope.$watch('items.selectedIdx', function(newVal, oldVal, scope) {
    if (newVal !== null) scroll.toCurrent();
  });

  $scope.load();
}

//Environment controllers
function EnvironmentListController($scope, $location, $resource, items, scroll) {
  //Model: UI
  $scope.showSummaries = true;
  $scope.showStatus = false;

  $scope.name = 'Environments';
  $scope.count = 0;
  items.all = [];
  $scope.items = items.all;  // bind only to shrunken array

  $scope.refresh = function() {
  };

  $scope.handleSpace = function() {
  };

  $scope.load = function() {
    console.log("Starting load");
    this.klass = $resource((checkmate_server_base || '') + '/:tenantId/environments/.json');
    this.klass.get({tenantId: $scope.auth.tenantId}, function(list, getResponseHeaders){
      console.log("Load returned");
      items.receive(list, function(item, key) {
        return {id: key, name: item.name, vendor: item.vendor, providers: item.providers};});
      $scope.count = items.count;
      $scope.items = items.all;
      console.log("Done loading");
    });
  };

  //Setup
  $scope.$watch('items.selectedIdx', function(newVal, oldVal, scope) {
    if (newVal !== null) scroll.toCurrent();
  });

  $scope.load();

  //Return text describing providers in the environment
  $scope.provider_list = function(environment) {
    list = [];
    if ('providers' in environment) {
        providers = environment.providers;
        if ('common' in providers)
            default_vendor = providers.common.vendor || '[missing vendor]';
        else
            default_vendor = '[missing vendor]';
        _.each(providers, function(provider, key, providers) {
            if (key == 'common')
                return;
            var name = provider.vendor || default_vendor;
            name += '.' + key;
            list.push(name);
        });
    }
    return list.join(", ");
  };
}


// Other stuff
if (Modernizr.localstorage) {
  // window.localStorage is available!
} else {
  alert("This browser application requires an HTML5 browser with support for local storage");
}
$(function() {
  // Don't close feedback form on click
  $('.dropdown input, .dropdown label, .dropdown textarea').click(function(e) {
    e.stopPropagation();
  });
});

document.addEventListener('DOMContentLoaded', function(e) {
  //On mobile devices, hide the address bar
  window.scrollTo(0, 0);

  //angular.bootstrap(document, ['checkmate']);
  $(".cmpop").popover();  //anything with a 'cmpop' class will attempt to pop over using the data-content and title attributes
  $(".cmtip").tooltip();  //anything with a 'cmtip' class will attempt to show a tooltip of the title attribute
  $(".cmcollapse").collapse();  //anything with a 'cmcollapse' class will be collapsible
}, false);

$(window).load(function () {
  //Init Google Code Prettifier
  prettyPrint();

  // Home page
  $(".pricing img.hover-fade").hover(
    function() {
      $(this).fadeTo(100, 1);
    },
    function() {
      $(this).fadeTo(100, 0.5);
  });
  $('#news-form').submit(function() {
    $.post('/newsletter/create', $('#news-form').serialize() , function(data) {
      $('#news-submit').html('Saved!');
    }, "json");
    return false;
  });
});
