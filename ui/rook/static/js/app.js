//Support for different URL for checkmate server in chrome extension
var is_chrome_extension = navigator.userAgent.toLowerCase().indexOf('chrome') > -1 && chrome && chrome.extension;
var checkmate_server_base = is_chrome_extension ? 'http://localhost\\:8080' : '';

//Load AngularJS
var checkmate = angular.module('checkmate', [
    'checkmate.filters',
    'checkmate.services',
    'checkmate.directives',
    'ngResource',
    'ngSanitize',
    'ngCookies',
    'ngLocale',
    'ngRoute',
    'ui.utils',
    'ui.bootstrap',
    'ui.codemirror',
    'ui.date',
    'checkmate.applications'
]);


//Load Angular Routes
checkmate.config(['$routeProvider', '$locationProvider', '$httpProvider', '$compileProvider', 'BlueprintDocsProvider', function($routeProvider, $locationProvider, $httpProvider, $compileProvider, BlueprintDocsProvider) {

  BlueprintDocsProvider.docs("/partials/blueprint_help.yaml.js");

  // Static Paths
  $routeProvider.when('/', {
    templateUrl: '/partials/home.html',
    controller: 'StaticController'
  })
  .when('/index.html', {
    templateUrl: '/partials/home.html',
    controller: 'StaticController'
  }).
  when('/readme', {
    templateUrl: '/partials/readme.html',
    controller: 'StaticController'
  });

  // New UI - static pages
  $routeProvider.when('/deployments/new/wordpress', {
    templateUrl: '/partials/managed-cloud-wordpress.html',
    controller: 'DeploymentManagedCloudController'
  })
  .when('/deployments/default', {  // for legacy compat for a while
    templateUrl: '/partials/managed-cloud-wordpress.html',
    controller: 'DeploymentManagedCloudController'
  })
  .when('/deployments/new', {
    templateUrl: '/partials/deployment-new-remote.html',
    controller: 'DeploymentNewRemoteController'
  })
  .when('/:tenantId?/blueprints/new', {
    templateUrl: '/partials/blueprints/new.html',
    controller: 'BlueprintNewController'
  })
  .when('/:tenantId?/blueprints/design/:owner?/:repo?/:flavor?', {
    templateUrl: '/partials/blueprints/design.html',
    controller: 'ConfigureCtrl',
    resolve: {
      deployment: function($route, github) {
        var owner = $route.current.params.owner;
        var repo = $route.current.params.repo;
        var flavor = $route.current.params.flavor;

        if(owner && repo) {
          return github.get_public_blueprint(owner, repo, flavor);
        }

        return undefined;
      }
    }
  })
  .when('/:tenantId/deployments/new', {
    templateUrl: '/partials/deployment-new-remote.html',
    controller: 'DeploymentNewRemoteController',
    reloadOnSearch: false
  })
  .when('/deployments/stacks/wordpress', {
    templateUrl: '/partials/wordpress-stacks.html',
    controller: 'StaticController'
  })
  .when('/deployments/stacks/magento', {
    templateUrl: '/partials/magento-stacks.html',
    controller: 'MagentoStackController'
  });

  // Admin pages
  $routeProvider.when('/admin/status/celery', {
    templateUrl: '/partials/raw.html',
    controller: 'RawController'
  })
  .when('/admin/status/libraries', {
    templateUrl: '/partials/raw.html',
    controller: 'RawController'
  })
  .when('/admin/feedback', {
    templateUrl: '/partials/admin-feedback.html',
    controller: 'FeedbackListController'
  })
  .when('/admin/deployments', {
    templateUrl: '/partials/deployments/index.html',
    controller: 'DeploymentListController'
  });

  // Auto Login
  $routeProvider.when('/autologin', {
    templateUrl: '/partials/autologin.html',
    controller: 'AutoLoginController'
  });

  // New UI - dynamic, tenant pages
  $routeProvider.when('/:tenantId/workflows/:id/status', {
    templateUrl: '/partials/workflow_status.html',
    controller: 'WorkflowController'
  })
  .when('/:tenantId/workflows/:id', {
    templateUrl: '/partials/workflow.html',
    controller: 'WorkflowController',
    reloadOnSearch: false
  })
  .when('/:tenantId/workflows-new/:id', {
    templateUrl: '/partials/workflow-new.html',
    controller: 'WorkflowController',
    reloadOnSearch: false
  })
  .when('/:tenantId/workflows', {
    templateUrl: '/partials/workflows.html',
    controller: 'WorkflowListController'
  })
  .when('/blueprints', {
    templateUrl: '/partials/blueprints/blueprints-remote.html',
    controller: 'BlueprintRemoteListController'
  })
  .when('/:tenantId/blueprints', {
    templateUrl: '/partials/blueprints/blueprints-remote.html',
    controller: 'BlueprintRemoteListController'
  })
  .when('/:tenantId/deployments', {
    templateUrl: '/partials/deployments/index.html',
    controller: 'DeploymentListController'
  })
  .when('/:tenantId/deployments/custom', {
    controller: 'ResourcesController',
    templateUrl: '/partials/resources/index.html'
  })
  .when('/:tenantId/deployments/:id', {
    controller: 'DeploymentController',
    templateUrl: '/partials/deployments/deployment.html'
  })
  .when('/:tenantId/providers', {
    controller: 'ProviderListController',
    templateUrl: '/partials/providers.html'
  })
  .when('/:tenantId/environments', {
    controller: 'EnvironmentListController',
    templateUrl: '/partials/environments.html'
  })
  .when('/404', {
    controller: 'StaticController',
    templateUrl: '/partials/404.html'
  })
  .otherwise({
    controller: 'StaticController',
    templateUrl: '/partials/404.html'
  });


  $locationProvider.html5Mode({enabled: true, requireBase: false});  //requireBase: true breaks SVG icons
  // Hack to get access to them later
  checkmate.config.header_defaults = $httpProvider.defaults;
  $httpProvider.defaults.headers.common.Accept = "application/json";
  $httpProvider.defaults.headers.post['Content-Type'] = "application/json;charset=utf-8";

  // Allow ssh, irc URLs
  $compileProvider.aHrefSanitizationWhitelist(/^\s*(https?|mailto|ssh|irc):/);
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
function StaticController($scope, $location, github) {
  $scope.showStatus = false;

  $scope.carousel_interval = -1; // Stopped
  $scope.spot_write_url = "https://one.rackspace.com/display/Checkmate/Checkmate+Blueprints+Introduction";
  $scope.item_base_url = "/deployments/new?blueprint=https:%2F%2Fgithub.rackspace.com%2FBlueprints%2F";
  $scope.devops_base_url = "/deployments/new?blueprint=https:%2F%2Fgithub.com%2FAutomationSupport%2F";
  $scope.deployments_list = [
    [
      {spot: "ready", show_name: true,  name: "Wordpress", description: null,                   url: $scope.devops_base_url + "wordpress", image: "wordpress.png"},
      {spot: "ready", show_name: true,  name: "Drupal",    description: "Managed Cloud Drupal", url: $scope.item_base_url + "drupal%23" + $scope.blueprint_ref, image: "druplicon.small_.png"},
      {spot: "ready", show_name: false, name: "PHP",       description: null,                   url: $scope.item_base_url + "php_app-blueprint%23" + $scope.blueprint_ref, image: "php.png"},
      {spot: "ready", show_name: true, name: "Magento",  description: "Digital Magento",      url: $scope.devops_base_url + "magentostack", image: "magento1-6.png"},
      {spot: "ready", show_name: true,  name: "Cassandra", description: null,                   url: $scope.item_base_url + "cassandra%23" + $scope.blueprint_ref, image: "cassandra.png"},
      {spot: "ready", show_name: true,  name: "MongoDB", description: null,       url: $scope.item_base_url + "mongodb-replicaset%23" + $scope.blueprint_ref, image: "mongodb.png"},
      {spot: "ready", show_name: true,  name: "MySQL",   description: null,       url: $scope.item_base_url + "mysql-server%23" + $scope.blueprint_ref, image: "mysql.png"}
    ],
    [
      {spot: "ready", show_name: true,  name: "Awwbomb", description: "Aww Bomb", url: $scope.item_base_url + "awwbomb%23" + $scope.blueprint_ref, image: "awwbomb.png"},
      {spot: "write", show_name: false, name: "Django",   description: null,                     url: null, image: "django_small.png"},
      {spot: "ready", show_name: false, name: "Rails",    description: "Rails 4",       url: $scope.item_base_url + "rails4_app-blueprint%23" + $scope.blueprint_ref, image: "rails.png"},
      {spot: "write", show_name: false, name: "NodeJS",   description: "node.js",       url: null, image: "nodejs.png"},
      {spot: "write", show_name: true,  name: "Tomcat",   description: null,                     url: null, image: "tomcat_small.gif"},
      {spot: "ready", show_name: false, name: "ZeroBin", description: null,       url: $scope.item_base_url + "zerobin%23" + $scope.blueprint_ref, image: "ZeroBin.png"},
      {spot: "ready", show_name: false, name: "Etherpad", description: "Etherpad Lite", url: $scope.item_base_url + "etherpad-lite%23" + $scope.blueprint_ref, image: "etherpad_lite.png"},

    ],
    [
      {spot: "write", show_name: true,  name: "DevStack", description: null,            url: null, image: "openstack.png"},
      {spot: "write", show_name: true,  name: "SugarCRM", description: "Managed Cloud SugarCRM", url: null, image: "sugarcrm-box-only.jpg"},
      {spot: "write", show_name: true,  name: "Magento",  description: "Managed Cloud Magento",  url: null, image: "magento1-6.png"},
      {spot: "write", show_name: true,  name: "Joomla", description: null, url: null, image: "joomla_small.png"},
      {spot: "write", show_name: false, name: "Apache", description: null, url: null, image: "apache.png"},
      {spot: "write", show_name: true,  name: "Hadoop", description: null, url: null, image: "hadoop.jpeg"},
      {spot: "write", show_name: true,  name: "Python", description: null, url: null, image: "python.png"}
    ]
  ];

  $scope.importGithubDeployment = function(form) {
    if(form.$valid) {
      $location.path("/blueprints/design/"+form.owner+"/"+form.repo);
    }
  };

  $scope.tabOnSlash = function($event, target) {
    if ($event.keyCode === 47) {
      $event.preventDefault();
      $(target).focus();
    }
  };

  $scope.display_name = function(item) {
    var name = null;
    if (item.show_name)
      name = item.name;
    return name;
  };

  $scope.in_spot = function(item /*, spots, ... */) {
    var in_spot = false;
    for (var spot=0 ; spot<=arguments.length ; spot++) {
      if (item.spot == arguments[spot])
        in_spot = true;
    }
    return in_spot;
  };

}

//Loads external page
function ExternalController($window, $location) {
  console.log("Loading external URL " + $location.absUrl());
  $window.location.href = $location.absUrl();
}

//Loads raw content
function RawController($scope, $location, $http) {
  console.log("Loading raw content from URL " + $location.absUrl());
  $http({method: 'GET', url: $location.absUrl()}).
    success(function(data, status, headers, config) {
      console.log(status);
      $scope.data = JSON.stringify(data, null, 2);
      $scope.safeApply();
    }).
    error(function(data, status, headers, config) {
      $scope.data = '';
      $scope.safeApply();
      $scope.show_error({
                      data: data,
                      status: status,
                      title: "Error",
                      message: "There was an error executing your request:"});
    });
}

function AutoLoginController($scope, $window, $cookies, $log, auth) {
  $scope.auto_login_success = function() {
    $window.location.href = '/';
  };

  $scope.auto_login_fail = function(response) {
    $window.location.href = '/';
  };

  $scope.accepted_credentials = ['tenantId', 'token', 'endpoint', 'username', 'api_key'];
  $scope.autoLogIn = function() {
    var creds = {};
    for (var i=0 ; i<$scope.accepted_credentials.length ; i++) {
      var key = $scope.accepted_credentials[i];
      creds[key] = $cookies[key];
      if (!creds[key] || creds[key] == "") delete creds[key];
      delete $cookies[key];
    }
    creds.endpoint = _.find(auth.endpoints, function(endpoint) { return endpoint.uri == creds.endpoint; } ) || {};

    $log.info("Submitting auto login credentials");
    return auth.authenticate(creds.endpoint, creds.username, creds.api_key, null, creds.token, null, creds.tenantId)
      .then($scope.auto_login_success, $scope.auto_login_fail);
  };
}

function ModalInstanceController($scope, $modalInstance, data) {
  angular.forEach(data, function(value, key) {
    $scope[key] = value;
  });

  $scope.close = function(response) {
    return $modalInstance.close(response);
  }

  $scope.dismiss = function(response) {
    return $modalInstance.dismiss(response);
  }
}

function LoginModalController($scope, $modalInstance, auth, $route) {

  $scope.dismiss = function(response) {
    return $modalInstance.dismiss({ logged_in: false, reason: 'dismissed' });
  }

  $scope.clear_login_form = function() {
    $scope.bound_creds.username = null;
    $scope.bound_creds.password = null;
    $scope.bound_creds.apikey   = null;
    auth.error_message = null;
  }

  $scope.on_auth_success = function() {
    $scope.auth.loading = false;
    $scope.select_unused_endpoint();
    $modalInstance.close({ logged_in: true });
    $route.reload();
  };

  $scope.on_auth_failed = function(response) {
    $scope.auth.loading = false;
    auth.error_message = '('+response.status+")";
  };

  // Log in using credentials delivered through bound_credentials
  $scope.logIn = function() {
    var username = $scope.bound_creds.username;
    var password = $scope.bound_creds.password;
    var apikey = $scope.bound_creds.apikey;
    var pin_rsa = $scope.bound_creds.pin_rsa;
    var endpoint = $scope.get_selected_endpoint();
    auth.error_message = null;
    $scope.auth.loading = true;

    return auth.authenticate(endpoint, username, apikey, password, null, pin_rsa, null)
      .then($scope.on_auth_success, $scope.on_auth_failed);
  };

  $scope.auth_error_message = function() { return auth.error_message; };

  $modalInstance.result.finally($scope.clear_login_form);
}

//Root controller that implements authentication
function AppController($scope, $http, $location, $resource, auth, $route, $q, $modal, $cookies, $cookieStore, github) {
  $scope.showHeader = true;
  $scope.showStatus = false;
  $scope.foldFunc = CodeMirror.newFoldFunction(CodeMirror.fold.brace);
  $scope.codemirrorLoaded = function(_editor){
    _editor.eachLine(function(line){
      if(line.text.substring(0,3) == '  "') {
        $scope.foldFunc(_editor, _editor.getLineNumber(line))
      }
    })
  }

  $scope.is_admin = function(strict) {
    return auth.is_admin(strict);
  };

  /* This method temporarily impersonates a user to allow submission of
     ATOMIC REQUESTS (i.e. requests that do not depend on other assynchronous
     requests to finish) under that user's credentials (only if current user
     is an admin and is not impersonating anybody).
     If you must submit requests that are chained to other requests,
     please refactor them to use the same headers as the initiating
     request. Since the admin can temporarily impersonate several
     different users in a short period of time, you cannot assume the
     the user's context will still be available at the time of subsequent
     requests. */
  $scope.wrap_admin_call = function(/* username, callback, args */) {
    var deferred = $q.defer();

    var args = Array.prototype.slice.call(arguments);
    var username = args.shift();
    var callback = args.shift();
    if (auth.is_admin(true)) {
      auth.impersonate(username, true).then(
        function(response) {
          var result = callback.apply($scope, args);
          auth.exit_impersonation();
          return deferred.resolve(result);
        },
        function(response) {
          return deferred.reject(response);
        }
      );
    } else {
      var result = callback.apply($scope, args);
      return deferred.resolve(result);
    }

    return deferred.promise;
  };

  $scope.is_impersonating = function() {
    return auth.is_impersonating();
  };

  $scope.remove_popovers = function() {
    _.each(angular.element('.popover').siblings('i'), function(el){
      angular.element(el).scope().tt_isOpen = false;
    });
    angular.element('.popover').remove();
  };

  $scope.add_popover_listeners = function(){
    angular.element('.entries').on('scroll', function(){
      $scope.$apply($scope.remove_popovers);
    });
  }
  $scope.$on('$viewContentLoaded', $scope.add_popover_listeners);

  $scope.check_token_validity = function(scope, next, current) {
    var token = auth.context.token;
    var now = new Date();

    if (token === undefined || token === null) return;
    var context_expiration = new Date(auth.context.token.expires || null);

    if (context_expiration <= now) {
      if (auth.is_impersonating()) {
        $scope.impersonate(auth.context.username)
          .then($scope.on_impersonate_success, $scope.on_impersonate_error);
      } else {
        var username = auth.context.username;
        auth.logOut();
        $scope.bound_creds.username = username;
        auth.error_message = "It seems your token has expired. Please log back in again.";
        $scope.loginPrompt();
      }
    }
  };
  $scope.$on('$routeChangeStart', $scope.check_token_validity);

  $scope.safeApply = function(fn) {
    var phase = this.$root.$$phase;
    if(phase == '$apply' || phase == '$digest') {
      if(fn && (typeof(fn) === 'function')) {
        fn();
      }
    } else {
      this.$apply(fn);
    }
  };

  $scope.navigate = function(url) {
    $location.path(url);
  };

  $scope.notifications = [];
  $scope.notify = function(message) {
    $scope.notifications.push(message);
  }

  //Call this with an http response for a generic error message
  $scope.show_error = function(response) {
    var error = response;
    // Also handle $http response
    if (typeof response == "object" && 'error' in response) {
      error = response.error;
      if (!('status' in error) && ('code' in error))
        error.status = error.code;
      if (!('data' in error) && ('description' in error))
        error.data = {description: error.description};
    }
    if (!('data' in error) && ('message' in error) && 'reason' in error)
      error.data = {error: error.message, description: error.reason};

    var info = {data: error.data,
                status: error.status,
                title: "Error",
                message: "There was an error executing your request:"};
    if (typeof error.data == "object" && 'description' in error.data)
        info.message = error.data.description;
    $scope.open_modal('/partials/app/_error.html', {error: info});
  };

  $scope.$on('logIn', function() {
    $scope.message = auth.message;
    $scope.notify("Welcome, " + $scope.auth.identity.username + "! You are logged in");
  });

  $scope.$on('logOut', function() {
    $location.url('/');
  });

  $scope.auth = auth;

  $scope.github = github;

  $scope.githubLogout = function() {
    $scope.github.logout();
    $scope.notify("Logged out of GitHub");
  };

  // Bind to logon modal
  $scope.bound_creds = {
    username: '',
    password: '',
    apikey: ''
  };

  // Using fades will cause two modals displayed in a row (e.g. warning + error)
  // to leave backdrop behind as of version ui-bootstrap-0.3.0
  $scope.modal_opts = {
    backdropFade: false,
    dialogFade: false
  };

  $scope.open_modal = function(template_name, data, scope, controller) {
    var config = {
      templateUrl: template_name,
      controller: controller || ModalInstanceController,
      scope: scope || $scope,
      resolve: {
        data: function() {
          return data || {};
        }
      }
    };
    var modal_instance = $modal.open(config);
    return modal_instance.result;
  };

  $scope.hidden_alerts = {};
  $scope.hide_alert = function(alert_id) {
    $scope.hidden_alerts[alert_id] = true;
  };
  $scope.display_alert = function(alert_id) {
    return !$scope.hidden_alerts[alert_id];
  };

  // Display log in prompt
  $scope.loginPrompt = function() {
    var data = {};
    var login_template = '/partials/app/login_prompt.html';
    return $scope.open_modal(login_template, data, $scope, LoginModalController);
  };

  $scope.uses_pin_rsa = function(endpoint) {
    return ($scope.get_selected_endpoint().scheme == "GlobalAuth");
  };

  $scope.is_active = function(endpoint) {
    if ($scope.get_selected_endpoint().uri == endpoint.uri)
      return "active";
    return "";
  };

  $scope.realm_name = function(endpoint) {
    return endpoint.realm.toLowerCase().replace(/[^a-z0-9]/g, '');
  }

  $scope.display_announcement = function() {
    return (auth.endpoints[0] !== undefined) && (auth.endpoints[0].realm == "Rackspace SSO");
  }

  $scope.is_hidden = function(endpoint) {
    return (endpoint.scheme == 'GlobalAuthImpersonation');
  };

  $scope.is_sso = function(endpoint) {
    return endpoint.uri == 'https://identity-internal.api.rackspacecloud.com/v2.0/tokens';
  };

  $scope.select_endpoint = function(endpoint) {
    auth.selected_endpoint = endpoint;
    localStorage.setItem('selected_endpoint', JSON.stringify(endpoint));
  };

  $scope.get_selected_endpoint = function() {
    var local_endpoint = localStorage.selected_endpoint || null;
    var selected = {};

    if(local_endpoint) {
      selected = JSON.parse(local_endpoint);
    } else if(!_.isEmpty(auth.selected_endpoint)) {
      selected = auth.selected_endpoint;
    } else if(auth.endpoints.length) {
      selected = auth.endpoints[0];
    }

    return selected;
  };

  $scope.select_unused_endpoint = function() {
    var selected = $scope.get_selected_endpoint();
    var endpoint = {};
    var endpoints = auth.endpoints;

    if(endpoints.length) {
      endpoints.every(function(_endpoint) {
        endpoint = _endpoint;
        return _endpoint.scheme == selected.scheme;
      });
    }

    $scope.select_endpoint(endpoint);
  };

  $scope.auth_provider_template_map = {
    'Rackspace SSO': {
      template: '/partials/app/auth_providers/rackspace_sso.tpl.html',
      scheme: 'GlobalAuth',
      label: 'Rackspace SSO',
      isVisible: function() {
        return auth.identity.endpoint_type == this.scheme;
      }
    },
    'US': {
      template: '/partials/app/auth_providers/rackspace_us.tpl.html',
      scheme: 'Keystone',
      label: 'US Cloud Account',
      isVisible: function() {
        return auth.identity.endpoint_type == this.scheme;
      }
    }
  };

  $scope.get_selected_endpoint_label = function() {
    var type = auth.identity.endpoint_type;
    var label = (_.filter($scope.auth_provider_template_map, function(endpoint) {
      return auth.identity.endpoint_type == endpoint.scheme;
    })[0] || {}).label;

    return label;
  };

  $scope.get_selected_form_template = function() {
    var realm = $scope.get_selected_endpoint().realm;
    return $scope.auth_provider_template_map[realm].template;
  };

  $scope.on_impersonate_success = function(response) {
    $scope.impersonation = { username: "" };
    var current_path = $location.path();
    var next_path = current_path;
    var account_number = /^\/[0-9]+/;
    var admin = /^\/admin/;
    if (current_path.match(account_number)) {
      next_path = current_path.replace(account_number, "/" + auth.context.tenantId);
    } else if (current_path.match(admin)) {
      next_path = current_path.replace(admin, "/" + auth.context.tenantId);
    }
    if (current_path == next_path)
      $route.reload();
    else
      $location.path(next_path);
  };

  $scope.on_impersonate_error = function(response) {
    var error = {
      data: response.data,
      status: response.status,
      title: "Error Impersonating User",
      message: "There was an error during impersonation:"
    };
    $scope.open_modal('/partials/app/_error.html', {error: error});
  }

  $scope.impersonation = { username: "" };
  $scope.impersonate = function(username) {
    $scope.impersonation.username = "";
    return auth.impersonate(username)
      .then($scope.on_impersonate_success, $scope.on_impersonate_error);
  };

  $scope.exit_impersonation = function() {
    auth.exit_impersonation();
    $location.url('/admin/deployments');
  };

  $scope.is_impersonating = function() {
    return auth.is_impersonating();
  };

  $scope.in_admin_context = function() {
    return auth.identity.is_admin && !auth.is_impersonating();
  };

  // Utility Functions
  var api = $resource((checkmate_server_base || '') + '/version');
  api.get(function(data, getResponseHeaders){
    $scope.api_version = data.version;
    $scope.api_git_commit = data['git-commit'];
    //Check if simulator enabled
    $scope.$root.simulator = getResponseHeaders("X-Simulator-Enabled");
    $scope.$root.clientId = getResponseHeaders("X-Github-Client-ID");
    //Check for which auth endpoints are enabled
    var headers;
    if ($.browser.mozilla) {
      // Firefox does not parse the headers correctly
      var all_headers = getResponseHeaders();
      var combined = '';
      _.each(all_headers, function(header_values, k) {
          if (k.indexOf('keystone') === 0) {
            _.each(header_values.split(', '), function(h){
              combined += ', ' + k.replace('keystone', 'Keystone') + ":" + h;
            });
          } else if (k.indexOf('globalauthimpersonation') === 0){
            _.each(header_values.split(', '), function(h){
              combined += ', ' + k.replace('globalauthimpersonation', 'GlobalAuthImpersonation')+ ":" + h;
            });
          } else if (k.indexOf('globalauth') === 0) {
            _.each(header_values.split(', '), function(h){
              combined += ', ' + k.replace('globalauth', 'GlobalAuth')+ ":" + h;
            });
          } else if (k == 'www-authenticate')
            _.each(header_values.split(', '), function(h){
              combined += ', ' + h;
            });
      });
      headers = combined.substring(2);
    }
    else {
      headers = getResponseHeaders("WWW-Authenticate");
    }
    auth.parseWWWAuthenticateHeaders(headers);
  });

  $scope.$root.blueprint_ref = 'master';
  var rook = $resource((checkmate_server_base || '') + '/rookversion');
  rook.get(function(rookdata, getResponseHeaders){
    $scope.rook_version = rookdata.version;
    $scope.$root.canonical_version = 'v' + rookdata.version.split('-')[0];
    if (rookdata.version.indexOf('dev') == -1)
      $scope.$root.blueprint_ref ='stable';
    console.log("Got rook version: " + $scope.rook_version);
    console.log("Got version: " + $scope.api_version);
    console.log("Blueprint ref to use: " + $scope.blueprint_ref);
  });

  //Check for a supported account
  $scope.is_unsupported_account = function() {
    var roles = [];
    var unsupported_roles = [];
    if ($scope.auth.identity.loggedIn === true)
        roles = $scope.auth.context.user.roles || [];
    return _.any(roles, function(role) {return unsupported_roles.indexOf(role.name) >= 0;});
  };

  //Check for a service level
  $scope.is_managed_account = function() {
    var roles = [];
    if ($scope.auth.identity.loggedIn === true)
        roles = $scope.auth.context.user.roles || [];
    return _.any(roles, function(role) {return role.name == "rax_managed";});
  };

  $scope.is_rack_connect_account = function() {
    var roles = [];
    if ($scope.auth.identity.loggedIn === true)
        roles = $scope.auth.context.user.roles || [];
    return _.any(roles, function(role) {return role.name == "rack_connect";});
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

  //Create environment based on catalog
  $scope.generate_default_environments = function() {
    var nova = {
      id: 'default_openstack',
      name: "Rackspace Open Cloud",
      description: "An OpenStack environment generated from the service catalog",
      providers: {
        'chef-solo': {vendor: 'opscode'},
        'load-balancer': {},
        'legacy': {},
        'database': {},
        'block': {},
        'common': {vendor: 'rackspace'}
      }
    };
    var legacy = {
      id: 'default_legacy',
      name: "Rackspace Legacy Cloud",
      description: "A legacy environment generated from the service catalog",
      providers: {
        'chef-solo': {vendor: 'opscode'},
        'load-balancer': {},
        'nova': {},
        'database': {},
        'block': {},
        'common': {vendor: 'rackspace'}
      }
    };
    return {default_openstack: nova, default_legacy: legacy};
  };

  //Return markdown as HTML
  $scope.render_markdown = function(raw) {
    if (raw !== undefined) {
      try {
        return marked(raw);
      } catch(err) {}
    }
    return '';
  };
}

function NavBarController($scope, $location, $http) {
  $scope.feedback = "";
  $scope.email = "";

  $scope.collapse_navbar = true;
  $scope.toggle_navbar = function() {
    $scope.collapse_navbar = !$scope.collapse_navbar;
  };

  $scope.hasPendingRequests = function() {
    return $http.pendingRequests.length > 0;
  };

  // Send feedback to server
  $scope.send_feedback = function() {
    data = JSON.stringify({
        "feedback": {
            "request": $scope.feedback,
            "email": $scope.email,
            "username": $scope.auth.identity.username,
            "tenantId": $scope.auth.context.tenantId,
            "location": $location.absUrl(),
            "auth": {
                "identity": $scope.auth.identity,
                "context": $scope.auth.context},
            "api_version": $scope.api_version,
            "rook_version": $scope.rook_version
            }
          });
    var headers = checkmate.config.header_defaults.headers.common;
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


function ActivityFeedController($scope, $http, items, github) {
  $scope.loading = false;
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
        try {
          parsed.action = event.payload.commits[0].message;
          parsed.action_url = event.payload.commits[0].url.replace('/api/v3/repos', '').replace('/commits/', '/commit/');
        } catch (err) {}
      }
      parsed.verb = event.payload.action;
    }
    var actionArray = event.type.match(/[A-Z][a-z]+/g).slice(0,-1);
    if (!parsed.verb) {
      parsed.verb = actionArray[0].toLowerCase();
      parsed.verb += parsed.verb.charAt(parsed.verb.length - 1) == 'e' ? 'd' : 'ed';
    }
    parsed.subject_type = actionArray.slice(1).join(' ').toLowerCase();
    parsed.article = '';
    switch(event.type)
    {
    case 'IssueCommentEvent':
      parsed.verb = 'issued';
      parsed.article = 'on';
      break;
    case 'CreateEvent':
      parsed.verb = 'created';
      break;
    case 'PullRequestEvent':
      parsed.subject_type = '';
      parsed.article = 'on';
      break;
    case 'PushEvent':
      parsed.article = 'to';
      break;
    case 'ForkEvent':
      break;
    case 'WatchEvent':
      parsed.verb = 'starred';
      break;
    default:
    }
    return parsed;
  };

  $scope.load = function() {
    if (github.config.url === 'https://github.com') {
      $scope.loading = true;
      var path = (checkmate_server_base || '') + '/githubproxy/orgs/checkmate/events';
      $http({method: 'GET', url: path, headers: {'X-Target-Url': 'https://api.github.com', 'accept': 'application/json'}}).
        success(function(data, status, headers, config) {
          var received_items = items.receive(data, $scope.parse_event);
          $scope.count = received_items.count;
          $scope.items = received_items.all;
          $scope.loading = false;
        }).
        error(function(data, status, headers, config) {
          $scope.loading = false;
        });
    } else if (github.config.url === 'https://github.rackspace.com') {
      $scope.loading = true;
      var path = (checkmate_server_base || '') + '/githubproxy/api/v3/orgs/Blueprints/events';
      $http({method: 'GET', url: path, headers: {'X-Target-Url': 'https://github.rackspace.com', 'accept': 'application/json'}}).
        success(function(data, status, headers, config) {
          var received_items = items.receive(data, $scope.parse_event);
          $scope.count = received_items.count;
          $scope.items = received_items.all;
          $scope.loading = false;
        }).
        error(function(data, status, headers, config) {
          $scope.loading = false;
        });
    }
  };
  $scope.load();
}

function TestController($scope, $location, $routeParams, $resource, $http, items, navbar, options, workflow) {
  $scope.prices = {
    single: {
      blueprint: 'https://github.com/checkmate/wordpress-single.git',
      core_price: '87.60',
      managed_price: '275.20'
    },
    double_dbaas: {
      blueprint: 'https://github.com/checkmate/wordpress-single-clouddb.git',
      core_price: '240.90',
      managed_price: '428.50',
      db_spec: '2 Gb Cloud Database'
    },
    double_mysql: {
      blueprint: 'https://github.com/checkmate/wordpress-single-db.git',
      core_price: '262.80',
      managed_price: '538.00',
      db_spec: '4 Gb Database Server'
    },
    multi_dbaas: {
      blueprint: 'https://github.com/checkmate/wordpress-clouddb.git',
      core_price: '478.15',
      managed_price: '694.95',
      db_spec: '4 Gb Cloud Database'
    },
    multi_mysql: {
      blueprint: 'https://github.com/checkmate/wordpress.git',
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
function WorkflowListController($scope, $location, $resource, workflow, items, navbar, scroll, pagination) {
  //Model: UI
  navbar.highlight("workflows");

  $scope.showPagination = function(){
    return $scope.links && $scope.totalPages > 1;
  };

  $scope.load = function() {
    console.log("Starting load");
    var path,
        query_params = $location.search(),
        paginator;

    paginator = pagination.buildPaginator(query_params.offset, query_params.limit);
    if (paginator.changed_params()) {
      $location.search('limit', paginator.limit)
      $location.search('offset', paginator.offset);
      $location.replace();
    }

    path = $location.path() + '.json';

    adjusted_params = {
        tenantId: $scope.auth.context.tenantId,
        offset: paginator.offset,
        limit: paginator.limit
    };

    params = _.defaults(adjusted_params, query_params)
    this.klass = $resource((checkmate_server_base || '') + path);
    this.klass.get(params, function(data, getResponseHeaders){
      var paging_info,
          workflows_url = '/' + $scope.auth.context.tenantId + '/workflows';

      console.log("Load returned");

      paging_info = paginator.getPagingInformation(data['collection-count'], workflows_url);

      var received_items = items.receive(data.results, function(item, key) {
        return {id: key, name: item.wf_spec.name, status: item.attributes.status, progress: item.attributes.progress, tenantId: item.tenantId};
      });
      $scope.count = received_items.count;
      $scope.items = received_items.all;
      $scope.currentPage = paging_info.currentPage;
      $scope.totalPages = paging_info.totalPages;
      $scope.links = paging_info.links;
      console.log("Done loading");
    });
  };
}

function WorkflowController($scope, $resource, $http, $routeParams, $location, $window, auth, workflow, scroll, deploymentDataParser, $timeout, $q, urlBuilder) {
  //Scope variables

  $scope.showStatus = true;
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

  $scope.hide_task_traceback = {
    failure: true,
    retry: true
  };

  $scope.toggle_task_traceback = function(task_type) {
    $scope.hide_task_traceback[task_type] = !$scope.hide_task_traceback[task_type];
  };

  $scope.urlBuilder = urlBuilder;

  // Called by load to refresh the status page
  $scope.reload = function(original_url) {
    // Check that we are still on the same page, otherwise don't reload
    if ($location.url() == original_url)
      $scope.load();
  };

  $scope.load = function() {
    var workflow_path = '/:tenantId/workflows/:id.json';
    try {
      var operation_path = $scope.data.operation.link + '.json';
      if (operation_path.indexOf('canvases') == -1)
          workflow_path = operation_path;
    } catch (err) {
      // Not all deployments have active operations
    }
    var deferred = $q.defer();
    this.klass = $resource((checkmate_server_base || '') + workflow_path);
    this.klass.get($routeParams,
                   function(object, getResponseHeaders){
      var deployments = $resource((checkmate_server_base || '') + '/:tenantId/deployments/:id.json');
      var params = angular.extend({}, $routeParams);
      if(object.attributes)
        params['id'] = object.attributes.deploymentId;

      $scope.deployment = deployments.get(params);

      $scope.data = object;
      $scope.tasks = workflow.flattenTasks({}, object.task_tree);
      var all_tasks = workflow.parseTasks($scope.tasks, object.wf_spec.task_specs);
      $scope.count = all_tasks.length;
      var statistics = workflow.calculateStatistics(all_tasks);
      $scope.totalTime = statistics.totalTime;
      $scope.timeRemaining = statistics.timeRemaining;
      $scope.taskStates = statistics.taskStates;
      $scope.percentComplete = (($scope.totalTime - $scope.timeRemaining) / $scope.totalTime) * 100;
      var path_parts = $location.path().split('/');
      if (path_parts.slice(-1)[0] == 'status' || path_parts.slice(2,3) == 'deployments') {
        if ($scope.taskStates.completed < $scope.count) {
          var original_url = $location.url();
          setTimeout(function() {$scope.reload(original_url);}, 2000);
        } else {
          var d = $resource((checkmate_server_base || '') + '/:tenantId/deployments/:id.json?with_secrets');
          d.get($routeParams, function(object, getResponseHeaders){

            $scope.output = deploymentDataParser.formatData(object);
            //Copy all data to all_data for clipboard use
            var all_data = [];
            all_data.push('From: ' + $location.absUrl());
            all_data.push('App URL: ' + $scope.output.path);
            all_data.push('App IP: ' +  $scope.output.vip);
            all_data.push('Servers: ');
            _.each($scope.output.resources, function(resource) {
                if (resource.component == 'linux_instance') {
                    all_data.push('  ' + resource.service + ' server: ' + resource['dns-name']);
                    try {
                      if (resource.instance.public_ip === undefined) {
                        for (var nindex in resource.instance.interfaces.host.networks) {
                            var network = resource.instance.interfaces.host.networks[nindex];
                            if (network.name == 'public_net') {
                                for (var cindex in network.connections) {
                                    var connection = network.connections[cindex];
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
                    } catch (err) {}
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
                      all_data.push('    Username:   ' + (resource.instance.interfaces.mysql.username || $scope.output.username));
                      all_data.push('    Password:   ' + (resource.instance.interfaces.mysql.password || $scope.output.password));
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
            if ($scope.output.username === undefined) {
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
            var error = {data: error.data, status: error.status, title: "Error loading deployment",
                         message: "There was an error loading your deployment:"};
            $scope.open_modal('/partials/app/_error.html', {error: error});
          });
        }
      } else if ($location.hash().length > 1) {
        $scope.selectSpec($location.hash());
        $('#spec_list').css('top', $('.summaryHeader').outerHeight() + 10); // Not sure if this is the right place for this. -Chris.Burrell (chri5089)
      } else
        $scope.selectSpec($scope.current_spec_index || Object.keys(object.wf_spec.task_specs)[0]);
      //$scope.play();
      deferred.resolve(object);
    }, function(response) {
        console.log("Error loading workflow.", response);
        var error = response.data.error;
        var info = {data: error,
                    status: response.status,
                    title: "Error Loading Workflow",
                    message: "There was an error loading your data:"};
        if (error !== undefined && 'description' in error)
            info.message = error.description;
      if ($location.path().indexOf('deployments') == -1)
        $scope.open_modal('/partials/app/_error.html', {error: info});
      deferred.reject(response);
    });

    return deferred.promise;
  };

  //Parse loaded workflow
  $scope.parse = function(object) {
      $scope.data = object;
      if (typeof object == 'object' && 'task_tree' in object) {
        $scope.tasks = workflow.flattenTasks({}, object.task_tree);
        var all_tasks = workflow.parseTasks($scope.tasks, object.wf_spec.task_specs);
        $scope.count = all_tasks.length;
        var statistics = workflow.calculateStatistics(all_tasks);
        $scope.totalTime = statistics.totalTime;
        $scope.timeRemaining = statistics.timeRemaining;
        $scope.taskStates = statistics.taskStates;
        $scope.percentComplete = (($scope.totalTime - $scope.timeRemaining) / $scope.totalTime) * 100;
      }
  };

  $scope.selectSpec = function(spec_id) {
    $scope.current_spec_index = spec_id;
    $scope.current_spec = $scope.data.wf_spec.task_specs[$scope.current_spec_index];
    $scope.current_spec_json = JSON.stringify($scope.current_spec, null, 2);

    var alltasks = $scope.tasks;
    var tasks = _.filter(alltasks, function(task, key) {
        return task.task_spec == spec_id;
      });
    $scope.current_spec_tasks = tasks;
    tasks = $scope.spec_tasks(spec_id);
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
            if (item !== null && typeof item !== 'undefined') {
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

    if (auth.identity.loggedIn) {
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
          var info = {data: error.data, status: error.status, title: "Error Saving",
                      message: "There was an error saving your JSON:"};
          $scope.open_modal('/partials/app/_error.html', {error: info});
        });
    } else {
      $scope.loginPrompt().then($scope.save_spec);
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

    $scope.current_task_json = JSON.stringify(copy, null, 2)
    // Refresh CodeMirror since it might have been hidden
    _.each($('.CodeMirror'), function(inst) { $timeout(function(){ inst.CodeMirror.refresh();}, 0) });
  };

  $scope.save_task = function() {
    var editor = _.find($('.CodeMirror'), function(c) {
      return c.CodeMirror.getTextArea().id == 'task_source';
      });

    if (auth.identity.loggedIn) {
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
          var info = {data: error.data, status: error.status, title: "Error Saving",
                      message: "There was an error saving your JSON:"};
          $scope.open_modal('/partials/app/_error.html', {error: info});
        });
    } else {
      $scope.loginPrompt().then($scope.save_task);
    }
  };

  //Return all tasks for a spec
  $scope.spec_tasks = function(spec_id) {
    return _.filter($scope.tasks || [], function(task, key) {
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

  $scope.is_paused = function() {
    return $scope.data && $scope.data.attributes.status == 'PAUSED';
  }

  $scope.workflow_action_success = function(response) {
    var action = response.config.url.replace($location.path() + '/+', '');
    $scope.notify("Command '" + action + "' workflow executed");
    $scope.load();
  }

  $scope.workflow_action_error = function(response) {
    $scope.show_error(response);
    var action = response.config.url.replace($location.path() + '/+', '');
  }

  $scope.workflow_action = function(workflow_id, action) {
    var retry = function() {
      $scope.workflow_action(workflow_id, action);
    };

    if (auth.identity.loggedIn) {
      console.log("Executing '" + action + " on workflow " + workflow_id);
      var action_url = $location.path() + '/+' + action;
      $http.get(action_url)
        .then($scope.workflow_action_success, $scope.workflow_action_error);
    } else {
      $scope.loginPrompt().then(retry);
    }
  };

  $scope.task_action = function(task_id, action) {
    var retry = function() {
      $scope.task_action(task_id, action);
    }

    if (auth.identity.loggedIn) {
      console.log("Executing '" + action + " on task " + task_id);
      $http({method: 'POST', url: $location.path() + '/tasks/' + task_id + '/+' + action}).
        success(function(data, status, headers, config) {
          $scope.notify("Command '" + action + "' task executed");
          // this callback will be called asynchronously
          // when the response is available
          $scope.load();
        }).error(function(data) {
          $scope.show_error(data);
        });
    } else {
      $scope.loginPrompt().then(retry);
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
        $scope.resource($scope.current_task, $scope.current_spec) !== null)
      return true;
    return false;
  };

  $scope.was_database_created = function() {
    if (typeof $scope.current_task != 'undefined' && ($scope.current_task.task_spec.indexOf("Create Database") === 0 || $scope.current_task.task_spec.indexOf("Add DB User") === 0) &&
        $scope.resource($scope.current_task, $scope.current_spec) !== null)
      return true;
    return false;
  };

  $scope.was_loadbalancer_created = function() {
    if (typeof $scope.current_task != 'undefined' && ($scope.current_task.task_spec.indexOf("Load") != -1 || $scope.current_task.task_spec.indexOf("alancer") != -1) &&
        $scope.resource($scope.current_task, $scope.current_spec) !== null)
      return true;
    return false;
  };

  $scope.resource = function(task, spec) {
    if (typeof task == 'undefined')
      return null;
    if (typeof spec == "undefined")
      return null;
    try {
      var resource_number = spec.properties.resource
      var res = _.find(task.attributes, function(obj, attr) {
        if (attr.indexOf("instance:" + resource_number) === 0)
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
  if (!auth.identity.loggedIn) {
    $scope.loginPrompt().then($scope.load);
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

    d3.select(".entries").select("svg").remove();

    var vis = d3.select(".entries").append("svg:svg")
        .attr("width", w)
        .attr("height", h);

    var nodes = _.map($scope.data.wf_spec.task_specs, function(t, k) {return t;});
    var links = [];
    _.each($scope.data.wf_spec.task_specs, function(t, k) {
        _.each(t.inputs, function(i) {
          links.push({"source": t, "target": $scope.data.wf_spec.task_specs[i]});
        });
      });

    var force = d3.layout.force()
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
        .attr("stroke", "black")
        .attr("stroke-width", 1)
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
        .data(nodes)
        .enter()
        .append("svg:g")
        .attr("class", "node")
        .call(node_drag);

    node.append("svg:text")
        .attr("class", "nodetext")
        .attr("dx", 12)
        .attr("dy", ".35em")
        .text(function(d) { return d.name; });

    node.append("svg:image")
        .attr("class", "circle")
        .attr("xlink:href", "/favicon.ico")
        .attr("x", "-8px")
        .attr("y", "-8px")
        .attr("width", "16px")
        .attr("height", "16px");

    force.on("tick", tick);

    function tick() {
      link.attr("x1", function(d) { return d.source.x; })
          .attr("y1", function(d) { return d.source.y; })
          .attr("x2", function(d) { return d.target.x; })
          .attr("y2", function(d) { return d.target.y; });

      node.attr("transform", function(d) { return "translate(" + d.x + "," + d.y + ")"; });
    }
    force.start();
  };

  /*======================================*/
  $scope._task_states = null;
  $scope.auto_refresh_timeout = { current: 2000, min: 2000, max: 60000 };
  $scope.auto_refresh_promise = null;

  // TODO: find a better way to decide if workflow is completed
  $scope.is_completed = function() {
    return ($scope.count === ($scope.taskStates['completed'] + $scope.taskStates['ready']))
  }

  $scope.reset_timeout = function() {
    $scope.auto_refresh_timeout.current = $scope.auto_refresh_timeout.min;
  }

  $scope.increase_timeout = function() {
    // Slowly increase timeout, but not too slowly
    $scope.auto_refresh_timeout.current += $scope.auto_refresh_timeout.current / 2;
    if ($scope.auto_refresh_timeout.current >= $scope.auto_refresh_timeout.max)
      $scope.auto_refresh_timeout.current = $scope.auto_refresh_timeout.max;
  }

  $scope.auto_refresh_success = function(response) {
    if (_.isEqual($scope._task_states, $scope.taskStates)) {
      $scope.increase_timeout();
    } else {
      $scope.reset_timeout();
    }

    if ($scope.is_completed()) {
      $scope.reset_timeout();
      return;
    }

    $scope.auto_refresh_promise = $timeout($scope.auto_refresh, $scope.auto_refresh_timeout.current);
    $scope._task_states = angular.copy($scope.taskStates);
  }

  $scope.auto_refresh = function() {
    $scope.load().then($scope.auto_refresh_success, $scope.increase_timeout);
  }

  $scope.toggle_auto_refresh = function() {
    if ($scope.auto_refresh_promise){
      $timeout.cancel($scope.auto_refresh_promise);
      $scope.auto_refresh_promise = null;
    } else {
      $scope.auto_refresh();
    }
  }
}

//Blueprint controllers
function BlueprintListController($scope, $location, $routeParams, $resource, items, navbar, options, workflow, blueprints, initial_blueprint, environments, initial_environment, DeploymentData) {
  //Model: UI
  $scope.showSummaries = true;
  $scope.showStatus = true;
  $scope.name = 'Blueprints';
  navbar.highlight("blueprints");

  $scope.environments = environments;
  $scope.environment = (typeof environments == "object" && Object.keys(environments).length >= 0) ? environments[initial_environment || Object.keys(environments)[0]] : null;
  var received_items = items.receive(blueprints, function(item, key) {
    return {key: key, id: item.id, name: item.name, description: item.description, selected: false};});
  $scope.items = received_items.all;
  $scope.count = received_items.count;

  $scope.selectItem = function(index) {
    $scope.selected = $scope.items[index];

    $scope.selected_key = $scope.selected.key;
  };

  for (var i=0;i<$scope.count;i++) {
    if ($scope.items[i].key == initial_blueprint) {
      console.log('Found and selecting initial blueprint');
      $scope.selectItem(i);
      break;
    }
  }
  if (typeof $scope.selected != 'object' && $scope.count > 0) {
    console.log('Selecting first blueprint');
    $scope.selectItem(index);
  }

  //Inherit from Deployment Initializer
  DeploymentNewController($scope, $location, $routeParams, $resource, options, workflow, $scope.selected, $scope.environment, DeploymentData);

  //Wire Blueprints to Deployment
  $scope.$watch('selected', function(newVal, oldVal, scope) {
    if (typeof newVal == 'object') {
       $scope.setBlueprint(blueprints[newVal.key]);
    }
  });
}

function BlueprintRemoteListController($scope, $location, $routeParams, $resource, $http, items, navbar, options, workflow, github, DeploymentData) {
  //Inherit from Blueprint List Controller
  BlueprintListController($scope, $location, $routeParams, $resource, items, navbar, options, workflow, {}, null, {}, null, DeploymentData);
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
  $scope.remote.api = {};
  $scope.remote.api.server = null;
  $scope.remote.api.url = null;

  $scope.parse_org_url = function(url) {
    console.log('parse_org_url', url);
    $scope.loading_remote_blueprints = true;
    github.parse_org_url(url).then(
      function(remote) {
        $scope.remote = remote;
        $scope.load();
      }
    );
  };

  $scope.remember_repo_url = function(remote_url) {
    if ($scope.remotes_used.indexOf(remote_url) == -1) {
      $scope.remotes_used.push(remote_url);
      localStorage.setItem('remotes', JSON.stringify($scope.remotes_used));
    }
  };

  $scope.load_remotes_used = function() {
    var data = localStorage.getItem('remotes');
    if (data !== undefined && data !== null)
      return JSON.parse(data);
    return ['https://github.com/checkmate'];
  };

  $scope.remotes_used = $scope.load_remotes_used();

  //Handle results of loading repositories
  $scope.receive_blueprints = function(data) {
    var sorted_items,
        sorted_items_object,
        object_to_replace,
        index_to_replace,
        blueprints = [],
        deleted_blueprints = [],
        cache_key = $scope.remote.owner + '_blueprints',
        cached_blueprints = JSON.parse(localStorage.getItem(cache_key) || "[]");

    function updateListWithBlueprint(list, blueprint){
      object_to_replace = _.findWhere(list, { id: blueprint.id });
      if(object_to_replace){
        index_to_replace = list.indexOf(object_to_replace);
      } else {
        index_to_replace = _.sortedIndex(list, blueprint, function(blueprint){ return blueprint.name.toUpperCase(); });
      }
      list[index_to_replace] = blueprint;
    }

    function updateBlueprintCache(blueprint_list, should_delete){
      blueprints = JSON.parse(localStorage.getItem(cache_key) || "[]");

      if(should_delete){
        blueprints = _.reject(blueprints, function(blueprint){
          return _.findWhere(blueprint_list, { id: blueprint.id });
        })
      } else {
        _.map(blueprint_list, function(item){ updateListWithBlueprint(blueprints, item)})
      }

      localStorage.setItem(cache_key, JSON.stringify(blueprints));
    }

    function verifyBlueprintRepo(blueprint){
      return github.get_contents($scope.remote, blueprint.api_url, "checkmate.yaml").then(
        function(content_data) {
          blueprint.is_blueprint_repo = true;
          updateBlueprintCache([blueprint]);
          blueprint.is_fresh = true;
          updateListWithBlueprint($scope.items, blueprint)
        }
      );
    }

    var received_items = items.receive(data, function(item, key) {
      if (!('documentation' in item))
        item.documentation = {abstract: item.description};
      return { key: item.id,
               id: item.html_url,
               name: item.name,
               description: item.documentation.abstract,
               git_url: item.git_url,
               ssh_url: item.ssh_url,
               selected: false,
               api_url: item.url,
               is_blueprint_repo: false };
    });

    $scope.count = received_items.count;
    $scope.loading_remote_blueprints = false;
    $('#spec_list').css('top', $('.summaryHeader').outerHeight());
    $scope.remember_repo_url($scope.remote.url);

    sorted_items = _.sortBy(received_items.all, function(item){ return item.name.toUpperCase(); });

    _.each(cached_blueprints, function(blueprint){
      if(_.findWhere(sorted_items, { id: blueprint.id }) === undefined){
        deleted_blueprints.push(blueprint);
      } else {
        blueprints.push(blueprint);
      }
    });

   _.each(deleted_blueprints, function(blueprint){
     updateBlueprintCache([blueprint], true);
   });

    $scope.items = blueprints.length > 0 ? blueprints : sorted_items;

    if(sorted_items.length >= 1) {
      _.reduce(sorted_items.slice(1),
               // Waiting on Angular 1.1.5 which includes an #always method. Until then, passing the same callback for both success and error to #then
               // See https://github.com/angular/angular.js/pull/2424
               function(memo, item) {
                 return memo.then(function(){ return verifyBlueprintRepo(item) },
                                  function(){ return verifyBlueprintRepo(item) }) },
               verifyBlueprintRepo(sorted_items[0]));
    }
  };

  $scope.load = function() {
    console.log("Starting load", $scope.remote.url);
    $scope.loading_remote_blueprints = true;
    github.get_repos($scope.remote).then(
      $scope.receive_blueprints, // Success
      function(response) { // Error
        $scope.loading_remote_blueprints = false;
        $scope.show_error(response.data);
    });
  };

  $scope.reload_blueprints = function() {
    console.log('reload_blueprints', $scope.remote);
    $scope.items = [];
    $scope.parse_org_url($scope.remote.url);
  };

  $scope.receive_branches = function(data) {
    $scope.branches = data;
    if (data.length >= 1) {
      var select = _.find(data, function(branch) {return branch.name == $scope.default_branch;});
      $scope.remote.branch = select || data[0];
      var found = _.find(data, function(branch) {return branch.name == 'stable';});
      if (found !== undefined) {
        found.url = ($scope.remote.repo.html_url || $scope.remote.repo.id) + '#stable';
        $scope.stable = found;
      } else
        delete $scope.stable;
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

  $scope.receive_blueprint = function(data, remote) {
    if ('environment' in data) {
      if (!('name' in data.environment))
        data.environment.name = "- not named -";
      if (!('id' in data.environment))
        data.environment.id = "included";
      var env_name = data.environment.name;
      $scope.environments = {env_name: data.environment};
    } else {
      //TODO: create from catalog
      $scope.environments = $scope.generate_default_environments();
    }
    $scope.environment = $scope.environments[Object.keys($scope.environments)[0]];
    $scope.remote = remote;

    if ('blueprint' in data) {
      $scope.blueprint = data.blueprint;
    } else {
      $scope.blueprint = null;
    }

    $scope.updateOptions();
  };

  $scope.loadBlueprint = function() {
    github.get_blueprint($scope.remote, $scope.auth.identity.username)
      .then(
        // Success
        function(checkmate_yaml) {
          $scope.receive_blueprint(checkmate_yaml, $scope.remote);
        },
        // Error
        function(response) {
          if (typeof data == 'string') {
            $scope.notify(data);
          } else {
            $scope.show_error(data);
          }
        }
      );
  };

  $scope.$watch('selected', function(newVal, oldVal, scope) {
    if (typeof newVal == 'object') {
      $scope.remote.repo = newVal;
      $scope.get_branches();  //calls loadBlueprint()
    }
  });

  $('#spec_list').css('top', $('.summaryHeader').outerHeight());
}

/*
 * Deployment controllers
 */
//Deployment list
function DeploymentListController($scope, $location, $http, $resource, scroll, items, navbar, pagination, auth, $q, cmTenant, Deployment, $timeout, $filter) {
  //Model: UI
  var STATUSES = [
    "ALERT",
    "DELETED",
    "DOWN",
    "FAILED",
    "NEW",
    "PLANNED",
    "UNREACHABLE",
    "UP"
  ]
  $scope.name = "Deployments";
  $scope.activeFilters = $location.search().status
  $scope.filter_list = _.map(STATUSES, function(status){
    var is_active = $scope.activeFilters === status || _.contains($scope.activeFilters, status);
    return { name: status, active: is_active };
  })

  $scope.build_filter = function(filter_name) {
    var default_values = $scope.filters.defaults[filter_name] || [];
    var search_params = $location.search()[filter_name] || [];
    var values = _.uniq(default_values.concat(search_params));

    var filter = _.map(values, function(value) {
      var is_active = (search_params == value || _.contains(search_params, value));
      return { name: value, active: is_active };
    });

    return filter;
  }

  $scope.filters = {};
  $scope.filters.defaults = {};
  $scope.default_tags = ['RackConnect', 'Managed', 'Racker', 'Internal'];
  $scope.filters.end_date = $location.search().end_date;
  $scope.filters.start_date = $location.search().start_date;
  $scope.filters.tenant_tag = _.map(_.uniq($scope.default_tags.concat($location.search().tenant_tag || [])), function(tag) {
    var is_active = ($location.search().tenant_tag == tag || _.contains($location.search().tenant_tag, tag));
    return { name: tag, active: is_active };
  });
  $scope.filters.defaults.blueprint_branch = ['master', 'stable'];
  $scope.filters.blueprint_branch = $scope.build_filter('blueprint_branch');

  $scope.query = $location.search().search;

  $scope.filter_deployments = function() {
    var filters = {};

    // Pagination
    var params = ['limit', 'offset'];
    var current_params = $location.search();
    for (var i=0 ; i<params.length ; i++) {
      var param = params[i];
      var param_value = current_params[param];
      if (param_value) filters[param] = param_value;
    }

    // Status
    var active_filters = _.where($scope.filter_list, { active: true });
    if (active_filters.length > 0) {
      var filter_names = _.map(active_filters, function(f){ return f.name })
      filters.status = filter_names;
    }

    // Tenant Tag
    var filter_list = ['tenant_tag', 'blueprint_branch'];
    for (var i=0 ; i<filter_list.length ; i++) {
      var filter_name = filter_list[i];
      var active_filters = _.where($scope.filters[filter_name], { active: true });
      if (active_filters.length > 0) {
        var filter_names = _.map(active_filters, function(f){ return f.name })
        filters[filter_name] = filter_names;
      }
    }

    // Dates
    if ($scope.filters.start_date)
      filters.start_date = $scope.filters.start_date
    if ($scope.filters.end_date)
      filters.end_date = $scope.filters.end_date

    // Search
    if ($scope.query) {
      filters.search = $scope.query;
    }

    $location.search( filters );
  }

  $scope.filter_promise = null;

  $scope.applyFilters = function(){
    if ($scope.filter_promise) {
      $timeout.cancel($scope.filter_promise);
    }
    $scope.filter_promise = $timeout($scope.filter_deployments, 1500);
  }

  $scope.has_pending_results = function() {
    if (!$scope.items) return true;
    if ($scope.filter_promise != null) return true;
    return false;
  }

  $scope.no_results_found = function() {
    if ($scope.has_pending_results()) return false;
    if ($scope.error_message) return false;

    var filter = $filter('filter');
    var filtered_results = filter($scope.items, $scope.query);

    return filtered_results.length == 0;
  }

  $scope.error_message = null;

  $scope.selected_deployments = { all: false };
  $scope.deployment_map = {};

  $scope.is_selected = function() {
    var keys = Object.keys($scope.selected_deployments);
    return keys.length != 1;
  }

  $scope.select_toggle = function(deployments, status) {
    if (!(deployments instanceof Array)) deployments = [deployments];
    var fixed_status = (status != undefined);

    for (var i=0 ; i< deployments.length ; i++) {
      var deployment = deployments[i];
      var toggle = !$scope.selected_deployments[deployment.id];
      var state = (fixed_status) ? status : toggle;
      if (state) {
        $scope.selected_deployments[deployment.id] = true;
        $scope.deployment_map[deployment.id] = deployment;
      } else {
        delete $scope.selected_deployments[deployment.id];
        delete $scope.deployment_map[deployment.id];
      }
    }

    var num_selected_deployments = _.keys($scope.deployment_map).length;
    $scope.selected_deployments.all = (num_selected_deployments == $scope.items.length);

  }

  $scope.sync_deployments = function() {
    var deferred = $q.defer();
    var promise = deferred.promise;
    var wrapped_call = function(deployment) {
      return function() {
        $scope.wrap_admin_call(deployment.created_by, $scope.sync, deployment);
      }
    };

    for (var id in $scope.selected_deployments) {
      var deployment = $scope.deployment_map[id];
      if (deployment) {
        promise = promise.finally(wrapped_call(deployment));
      }
    }

    deferred.resolve();
    return promise;
  }

  navbar.highlight("deployments");

  //Model: data
  $scope.count = 0;

  $scope.showPagination = function(){
    return $scope.links && $scope.totalPages > 1;
  };

  $scope.load = function() {
    var query_params = $location.search(),
        paginator,
        params;

    paginator = pagination.buildPaginator(query_params.offset, query_params.limit);
    if (paginator.changed_params()) {
      $location.search('limit', paginator.limit);
      $location.search('offset', paginator.offset);
      $location.replace();
    }

    adjusted_params = {
        tenantId: auth.context.tenantId,
        offset: paginator.offset,
        limit: paginator.limit
    };

    params = _.defaults(adjusted_params, query_params)
    this.klass = $resource((checkmate_server_base || '') + $location.path() + '.json');
    this.klass.get(params,
      // Success
      function(data, getResponseHeaders){
        var paging_info,
            deployments_url = $location.url();

        paging_info = paginator.getPagingInformation(data['collection-count'], deployments_url);

        var received_items = items.receive(data.results, function(item) {
          return {id: item.id, name: item.name, created: item.created, created_by: item['created-by'], tenantId: item.tenantId,
                  blueprint: item.blueprint, environment: item.environment, operation: item.operation,
                  status: item.status, display_status: Deployment.status(item),
                  progress: Deployment.progress(item)};
        });
        $scope.error_message = null;
        $scope.count = received_items.count;
        $scope.items = received_items.all;
        $scope.currentPage = paging_info.currentPage;
        $scope.totalPages = paging_info.totalPages;
        $scope.links = paging_info.links;

        var tenant_ids = $scope.get_tenant_ids($scope.items);
        $scope.load_tenant_info(tenant_ids)
          .then($scope.mark_content_as_loaded, $scope.mark_content_as_loaded);
      },
      // Error
      function(response) {
        $scope.items = [];
        $scope.error_message = response.data.error.explanation;
      }
    );
  };


  $scope.sync_success = function(response){
    if (response)
      $scope.notify(response.data.length + ' resources synced');
  }

  $scope.sync_failure = function(error){
    var info = {data: error.data, status: error.status, title: "Error Syncing",
                message: "There was an error syncing your deployment"};
    $scope.open_modal('/partials/app/_error.html', {error: info});
  }

  // This also exists on DeploymentController - can be refactored
  $scope.sync = function(deployment) {
    var retry = function() {
      $scope.sync(deployment);
    };

    if (auth.is_logged_in()) {
      Deployment.sync(deployment).then($scope.sync_success, $scope.sync_failure);
    } else {
      $scope.loginPrompt().then(retry);
    }
  };

  $scope.admin_sync = function(deployment) {
    var tenant_id = deployment.tenantId;
    var username = "rackcloudtech"; // TODO: get username from tenant_id
    auth.impersonate(username).then(function() {
      $scope.sync(deployment);
      auth.exit_impersonation();
    });
  }

  $scope.__tenants = {};
  $scope.__content_loaded = false;
  $scope.tenant_tags = function(tenant_id) {
    var tags = $scope.__tenants[tenant_id] && $scope.__tenants[tenant_id].tags;
    return (tags || []);
  };

  $scope.all_tags = function() {
    var tenants = _.values($scope.__tenants);
    var all_tags = _.flatten(_.map(tenants, function(tenant) { return tenant.tags }));
    var unique_tags = _.uniq(all_tags);
    var custom_tags = _.filter(unique_tags, function(tag) { return $scope.default_tags.indexOf(tag) === -1 })
    return $scope.default_tags.concat(custom_tags);
  }

  $scope.get_tenant = function(tenant_id) {
    var tenant = $scope.__tenants[tenant_id];
    if (!tenant) {
      tenant = cmTenant.get(tenant_id);
      $scope.__tenants[tenant_id] = tenant;
    }
    tenant.id = tenant_id;
    return tenant;
  }

  $scope.toggle_tag = function(tenant_id, tag) {
    if ($scope.has_tag(tenant_id, tag)) {
      $scope.remove_tag(tenant_id, tag);
    } else {
      $scope.add_tag(tenant_id, tag);
    }
  }

  $scope.add_tag = function(tenant_id, new_tag) {
    var tenant = $scope.get_tenant(tenant_id);
    cmTenant.add_tag(tenant, new_tag);
  }

  $scope.remove_tag = function(tenant_id, old_tag) {
    var tenant = $scope.get_tenant(tenant_id);
    cmTenant.remove_tag(tenant, old_tag);
  }

  $scope.has_tag = function(tenant_id, tag) {
    if ($scope.__content_loaded) {
      var tenant = $scope.get_tenant(tenant_id);
      return (tenant.tags && tenant.tags.indexOf(tag) !== -1);
    }

    return false;
  }

  $scope.get_tenant_ids = function(deployments) {
    var all_ids = _.map(deployments, function(deployment) { return deployment.tenantId; });
    var unique_ids = _.uniq(all_ids);
    return _.compact(unique_ids);
  };

  $scope.load_tenant_info = function(tenant_ids) {
    var promises = [];
    tenant_ids = tenant_ids || [];

    if (auth.is_admin()) {
      tenant_ids.forEach(function(id) {
        if (!id) return;

        var deferred = $q.defer();
        promises.push(deferred.promise);
        $scope.__tenants[id] = cmTenant.get(id, deferred.resolve, deferred.reject);
      });
    }

    return $q.all(promises);
  };

  $scope.mark_content_as_loaded = function() {
    $scope.__content_loaded = true;
  };

  $scope.is_content_loaded = function() {
    return $scope.__content_loaded;
  };
}

//Hard-coded for Managed Cloud Wordpress
function DeploymentManagedCloudController($scope, $location, $routeParams, $resource, $http, items, navbar, options, workflow, github, DeploymentData) {

  $scope.receive_blueprint = function(data, remote) {
    if ('blueprint' in data) {
      if ($scope.auth.identity.loggedIn === true) {
        data.blueprint.options.region['default'] = $scope.auth.context.user['RAX-AUTH:defaultRegion'] || $scope.auth.context.regions[0];
        data.blueprint.options.region.choice = $scope.auth.context.regions;
      }
      WPBP[remote.url] = data.blueprint;
      var new_blueprint = {};
      new_blueprint[remote.url] = data.blueprint;
      var received_items = items.receive(new_blueprint, function(item, key) {
        return {key: remote.url, id: item.id, name: item.name, description: item.description, remote: remote, selected: false};
      });
      $scope.items.push(received_items.all[0]);
      $scope.count = $scope.items.length;
    }
  };

  $scope.loadRemoteBlueprint = function(repo_url) {
    var remote = github.parse_url(repo_url);
    var uri = URI(repo_url);
    var ref = uri.fragment() || 'master';
    github.get_branch_from_name(remote, ref)
      .then(
        // Success
        function(branch) {
          remote.branch = branch;
          github.get_blueprint(remote, $scope.auth.identity.username)
            .then(
              // Success
              function(checkmate_yaml) {
                $scope.receive_blueprint(checkmate_yaml, remote);
              },
              // Error
              function(response) {
                $scope.notify('['+response.status+'] ' + 'Unable to load "'+ref+'" version of '+remote.repo.name+' from '+remote.server);
              }
            );
        },
        // Error
        function(response) {
          $scope.notify('['+response.status+'] ' + 'Unable to find branch or tag "'+ref+'" of '+remote.repo.name+' from '+remote.server);
        }
      );
  };

  //Default Environments
  var ENVIRONMENTS = {
      "legacy": {
          "description": "This environment uses legacy cloud servers.",
          "name": "Legacy Cloud Servers",
          "providers": {
              "legacy": {},
              "chef-solo": {
                  "vendor": "opscode",
                  "provides": [
                      {
                          "application": "http"
                      },
                      {
                          "application": "ssh"
                      },
                      {
                          "database": "mysql"
                      },
                      {
                          "compute": "mysql"
                      }
                  ],
                  constraints: [ {source: "%repo_url%"} ]
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
              "chef-solo": {
                  "vendor": "opscode",
                  "provides": [
                      {
                          "application": "http"
                      },
                      {
                          "application": "ssh"
                      },
                      {
                          "database": "mysql"
                      },
                      {
                          "compute": "mysql"
                      }
                  ],
                  constraints: [ {source: "%repo_url%"} ]
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

  $scope.setAllBlueprintRegions = function() {
    _.each(WPBP, function(value, key) {
      value.options.region['default'] = $scope.auth.context.user['RAX-AUTH:defaultRegion'] || $scope.auth.context.regions[0];
      value.options.region.choice = $scope.auth.context.regions;
    });
  };

  if ($scope.auth.identity.loggedIn === true) {
      $scope.setAllBlueprintRegions();
  }

  //Show list of supported Managed Cloud blueprints
  BlueprintListController($scope, $location, $routeParams, $resource, items, navbar, options, workflow,
                          WPBP, null, ENVIRONMENTS, 'next-gen', DeploymentData);

  $scope.updateDatabaseProvider = function() {
    if ($scope.blueprint.id == '0255a076c7cf4fd38c69b6727f0b37ea') {
        //Remove DBaaS Provider
        if ('database' in $scope.environment.providers)
            delete $scope.environment.providers.database;
        //Add database support to chef provider
        $scope.environment.providers['chef-solo'].provides[2] = {database: "mysql"};
    } else if ($scope.blueprint.id == 'd8fcfc17-b515-473a-9fe1-6d4e3356ef8d') {
        //Add DBaaS Provider
        $scope.environment.providers.database = {};
        //Remove database support from chef-local
        if ($scope.environment.providers['chef-solo'].provides.length > 2)
            $scope.environment.providers['chef-solo'].provides.pop(2);
        if ($scope.environment.providers['chef-solo'].provides.length > 2)
            $scope.environment.providers['chef-solo'].provides.pop(2);
    }
  };

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

  $scope.$watch('selected', function(newVal, oldVal, scope) {
    if (typeof newVal == 'object') {
      $scope.remote = $scope.selected.remote;
      $scope.stable = {url: $scope.remote.url.replace('#' + $scope.remote.branch.name, '') + '#stable'};
    }
  });

  //Load the latest supported blueprints (tagged as stable) from github
  $scope.loadWordpressBlueprints = function(){
    $scope.items = [];
    $scope.loadRemoteBlueprint('https://github.com/checkmate/wordpress#stable');
    $scope.loadRemoteBlueprint('https://github.com/checkmate/wordpress-clouddb#stable');

    //Load the latest master from github
    $scope.loadRemoteBlueprint('https://github.com/checkmate/wordpress#master');
    $scope.loadRemoteBlueprint('https://github.com/checkmate/wordpress-clouddb#master');
  }

  $('#mcspec_list').css('top', $('.summaryHeader').outerHeight()); // Not sure if this is the right place for this. -Chris.Burrell (chri5089)
}

//Select one remote blueprint
function DeploymentNewRemoteController($scope, $location, $routeParams, $resource, $http, items, navbar, options, workflow, github, DeploymentData) {

  var blueprint = $location.search().blueprint;
  if (blueprint === undefined)
    blueprint = "https://github.com/checkmate/helloworld";
  var u = URI(blueprint);
  if (u.fragment() === "") {
    u.fragment($location.hash() || 'master');
    $location.hash("");
    $location.search('blueprint', u.normalize());
  }

  BlueprintRemoteListController($scope, $location, $routeParams, $resource, $http, items, navbar, options, workflow, github, DeploymentData);

  //Override it with a one repo load
  $scope.load = function() {
    console.log("Starting load", $scope.remote);
    $scope.loading_remote_blueprints = true;
    github.get_repo($scope.remote, $scope.remote.repo.name,
      function(data) {
        $scope.remote.repo = data;
        $scope.default_branch = u.fragment() || $location.hash() || 'master';
        $scope.selected = $scope.remote.repo;
      },
      function(data) {
        $scope.loading_remote_blueprints = false;
        $scope.show_error(data);
      });
  };

  //Instead of parse_org_url
  $scope.loading_remote_blueprints = true;
  github.parse_org_url(blueprint).then(function(remote) {
    $scope.remote = remote;
    $scope.load();
  });
}

// Handles the option option and deployment launching
function DeploymentNewController($scope, $location, $routeParams, $resource, options, workflow, blueprint, environment, DeploymentData) {
  $scope.environment = environment;
  $scope.options = [];
  $scope.inputs = {};
  $scope.deployment_name = '';
  $scope.domain_names = null;
  $scope.manual_site_address = null;
  $scope.show_site_address_controls = false;

  $scope.submitting = false; //Turned on while we are processing a deployment


  //Retrieve existing domains
  $scope.getDomains = function(){
    $scope.domain_names = [];
    var tenant_id = $scope.auth.context.tenantId;
    if ($scope.auth.identity.loggedIn && tenant_id){
      var url = '/:tenantId/providers/rackspace.dns/resources';
      var Domains = $resource((checkmate_server_base || '') + url, {tenantId: $scope.auth.context.tenantId});
      var results = Domains.query(function() {
        for(var i=0; i<results.length; i++){
          $scope.domain_names.push(results[i].name);
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
    $scope.updateOptions();
  };

  $scope.setEnvironment = function(environment) {
    $scope.environment = environment;
    $scope.updateRegions();
  };

  $scope.updateRegions = function() {
    if ($scope.environment) {
      if ('providers' in $scope.environment && 'legacy' in $scope.environment.providers) {
        if ($scope.options && $scope.auth.identity.loggedIn === true && 'RAX-AUTH:defaultRegion' in $scope.auth.context.user) {
            _.each($scope.options, function(option) {
                if (option.id == 'region') {
                    option['default'] = $scope.auth.context.user['RAX-AUTH:defaultRegion'];
                    option.choice = [option['default']];
                    $scope.inputs[option.id] = option['default'];
                    option.description = "Your legacy cloud servers region is '" + option['default'] + "'. You can only deploy to this region";
                }
            });
        }
      } else {
        _.each($scope.options, function(option) {
          if (option.id == 'region' && $scope.auth.identity.loggedIn === true) {
            option.choice = $scope.auth.context.regions;
            option.description = "";
          }
        });
      }
    }
  };

  $scope.updateOptions = function() {
    $scope.options = [];
    $scope.option_groups = {};
    $scope.options_to_display = [];
    $scope.option_headers= {};
    $scope.region_option = null;
    $scope.inputs = {};

    if ($scope.blueprint) {
      var opts = options.getOptionsFromBlueprint($scope.blueprint);
      $scope.options = $scope.options.concat(opts.options);
      $scope.option_groups = opts.groups;
      $scope.region_option = opts.region_option;
      $scope.options_to_display = opts.options_to_display;
      $scope.option_headers = opts.option_headers;
    }

    if ($scope.environment) {
      $scope.options = $scope.options.concat(options.getOptionsFromEnvironment($scope.environment));
      $scope.updateRegions();
    }

    _.each($scope.options, function(option) {
      if ('default' in option && (typeof option['default'] != 'string' || option['default'].indexOf('=generate') === -1)) {
        $scope.inputs[option.id] = option['default'];
      } else
        $scope.inputs[option.id] = null;
      if (option.id == 'region' && $scope.auth.identity.loggedIn === true)
        option.choice = $scope.auth.context.regions;
    });
    $scope.show_site_address_controls = _.any($scope.options, function(option) {return ['domain', 'web_server_protocol'].indexOf(option.id) > -1;});
    if (_.any($scope.options, function(option) {
        if (option.id == 'domain')
          return true;
        if ('type' in option && option['type'] == 'url')
          return true;
        return false;
        }) && $scope.domain_names === null)
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
    $scope.inputs['web_server_protocol'] = parsed.protocol;
    $scope.inputs['domain'] = parsed.hostname;
    $scope.inputs['path'] = parsed.path || "/";
  };

  $scope.UpdateURLOption = function(scope, option_id) {
    if ($scope.AcceptsSSLCertificate(scope) === true) {
      $scope.inputs[option_id] = {
        url: scope.url,
        certificate: scope.certificate,
        private_key: scope.private_key,
        intermediate_key: scope.intermediate_key
      };
    } else
      $scope.inputs[option_id] = scope.url;
  };

  $scope.UpdateURL = function(scope, option_id) {
    var new_address = scope.protocol + '://' + scope.domain + scope.path;
    var parsed = URI.parse(new_address);
    scope.url = new_address;
    $scope.UpdateURLOption(scope, option_id);
  };

  $scope.UpdateParts = function(scope, option_id) {
    var input = scope.url || $scope.inputs[option_id];
    var address = input.url || input;
    var parsed = URI.parse(address);
    scope.protocol = parsed.protocol;
    scope.domain = parsed.hostname;
    scope.path = parsed.path;
  };

  $scope.AcceptsSSLCertificate = function(scope) {
    if ((scope.option['encrypted-protocols'] || []).indexOf(scope.protocol) > -1)
      return true;
    if (scope.option['always-accept-certificates'] === true)
      return true;
    return false;
  };

  $scope.ShowCerts = function() {
    if ('web_server_protocol' in $scope.inputs && $scope.inputs['web_server_protocol'].indexOf('https') != -1)
      return true;
    if ('url' in $scope.inputs && $scope.inputs['url'].indexOf('https') != -1)
      return true;
    return false;
  };

  $scope.showOptions = function() {
    return ($scope.environment && $scope.blueprint);
  };

  $scope.prepDeployment = function(action) {
    var response = {};
    var url = '/:tenantId/deployments';
    if (action)
      url += '/' + action;
    var Deployment = $resource((checkmate_server_base || '') + url, {tenantId: $scope.auth.context.tenantId});
    var deployment = new Deployment({});
    if ($scope.deployment_name !== undefined && $scope.deployment_name.trim().length > 0)
        deployment.name = $scope.deployment_name;
    deployment.blueprint = jQuery.extend({}, $scope.blueprint);  //Copy
    deployment.environment = jQuery.extend({}, $scope.environment);  //Copy
    deployment.inputs = {};
    deployment.inputs.blueprint = {};
    var remote = $scope.selected.remote || $scope.remote;
    if (typeof remote == 'object' && remote.url !== undefined)
      options.substituteVariables(deployment, {"%repo_url%": remote.url});

    var break_flag = false;
    var errors = [];
    response.errors = errors;

    // Have to fix some of the inputs so they are in the right format, specifically the select
    // and checkboxes. This is lame and slow and I should figure out a better way to do this.
    _.each($scope.inputs, function(element, key) {
      var option = _.find($scope.options, function(item) {
        if (item.id == key)
          return item;
        return null;
      });

      if (option === undefined){
        console.log("WARNING: expected option '" + key + "' is undefined");
        return;
      }

      //Check that all required fields are set
      if (option.required === true) {
        if ($scope.inputs[key] === null) {
          err_msg = "Required field "+key+" not set. Aborting deployment.";
          errors.push[err_msg];
          break_flag = true;
        }
      }

      if (option.type === "boolean") {
        if ($scope.inputs[key] === null) {
          deployment.inputs.blueprint[key] = false;
        } else {
          deployment.inputs.blueprint[key] = $scope.inputs[key];
        }
      } else {
        deployment.inputs.blueprint[key] = $scope.inputs[key];
      }
    });

    response.break_flag = break_flag;

    // Temp hack to set chef server credentials
    if (deployment.environment.providers && deployment.environment.providers['chef-server']) {
      if (!deployment.inputs) {
        deployment.inputs = {};
      };
      if (!deployment.inputs.blueprint) {
        deployment.inputs.blueprint = {};
      };
      _.extend(deployment.inputs.blueprint,
        {
          "chef-server-user-key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEpQIBAAKCAQEAuWhEX/K00A7Phuxcz6ltb412hnxiocAoV4CzFwDpk6JsIGAK\nUCc0Uc6UR/cZ8tMOsggST2InnOJiuwB4aNpdJi6JIXNh0Q1PtlDr8WlSDPESB5Ms\nZf1zud/23d/jKdPeYhnQzmjcdzhxbiPPbBO1U3ZrAy03d17RszGDjHvsOYyMdP8U\nbZanujE8078in2ph4A9fZb7QwiiqHgHG8f6M7CttJJ/HEAR32w4ElMgIN8JJegTS\n17EK6o3euAcdVN5r7LkjYDy6fFR1sHLE1Y+7svcCmZT2CJkfxjKlTt9w1ZGd2lAN\n1wfCqj7nM3ImxfbNAhnMByGCo5XHuMDhKvJ3rQIDAQABAoIBAQCq5O95HOYKjEw+\nyeh2RG2pj9O6/DWRb+P/W5I3VtD1EpXldYCsBqbT7LyCZMHXLzDxaj0uTIPEuGpW\ngYV66CNJyUT+vzJfFYzuuEHx/6jwYtfCgaY/z9D2d/g85FunNzFYbQEo8ECd5zmu\nUnWi4buV1aWnhOsGLTDOoYnmWGcRVuhXYxvGsJiFOIbLuEfcaYPdYnTmpGZ5NLJd\n2SAs/KWgIumRNh2bL8rjFTGH8z5DSt4bhizxdzC6SqouDwVPcWYUuT6cNYOxi5TK\ndEiOEJpXAO9TUqUfE5R3p2e64bezbF8nFYbAbwadOSIca2bhJAJX+/H5Vl3Ml8zG\nb/Um0a3hAoGBAOF5aHf+w842+zNzcpntnGW7boY/A0utz3Jed/tdaWD+bRPXR3Eb\n5Kqk/rRMInRwV7bBO4zQ9IhwEHmIhsDsqZ+gXmFN3+plQ18H/AELVPMb5vjAj/0s\nqFgMX+BZv+DA5K29hxJ4lqaRKGZr8cNHKi2vZIuGesBoNwW8NAc1P5/FAoGBANKC\nMx74XAe8fq3Ba0X7hqAsE8RGXxyMc07m4YqPz8Ib12NBqIFYKbFOFHs0btBf7P5P\n/WB0m6xoCl4eLQq6SIPNy9DeXfLzczqUGbRMg+t7iC6dZXE1cUNbkpFHc5KnD7rZ\nLLfB33Kx0KtQHf3KmntCJ0pSE0Hh6MxGcqvZEE7JAoGBAN1V3xWcQ/6Uvnc9Z0xv\nkk3TdqXWCZgq4S92SPW6Nw399Hm7pOgF560UFuxKqLAA8Dn46kpLfSDKUYHcYdvU\n9pY6SSvf1GU2TrJlFh64TwXvaAbckPyI8CCu1RdZQyCQemuLV6LsOYb9i9kvMb7u\nhxsdx+endayXIRxCKhjBTtm5AoGBANBlIpSjTABAo6wB0d/bDECewgbJn7jUdgaD\nXH5etk80XrsdMeKyU7v6Tx5VHurcO/LbXzvQ1JgN+02HVBHNrqIE5qPkr18nkUhJ\ne1TZdrN1fLChEt7LCFClY+i8snZZOqJAAxv7KukRjUE7NCWeH+ar69eQfw32xg8M\nItNrNNC5AoGALMFodBcRLEsfHunzsBe66F2mnx8qO9HoTYuJcBCdvz0DYxvXHS60\nRAu3iCOwMMIiUZkc1/xize0aCNvxaLZO5hduLhLSSZfjC1HXFx9HQKcbEXIk+K0A\nTgIT2DvqGKO2EYLiErkWHN7LVkyt9qZJ4m1tFfwlfG2jTUoYB9maZRw=\n-----END RSA PRIVATE KEY-----\n",
          "chef-server-username": "ziadsawalha",
          "validator-pem": "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEAxqZ1OqmpU2AQMnFCToLLW23J9dPvCNJ81XaM3c3PEyJS9rkx\n2u29oOEWjEybwBn0UgoMMJEhK/4G1zVG176xNEsr6iYQ6aOs3x7R3IeRP5fwBxwY\nbuZonZ8vTQuZ+ZIrawy10XqYrlgb6w+oKTnzwYDWfwBU13UZjXA5d/8RECYrfojS\nNWRXI3k1H6WXjb9l2x/IFcjt+WmQeA23tBFnFuPF1Gn3vkzFXKRJH/cKS6eCigoy\nl2RA+7IDMPMmATCE4T3VO5Rplr0OYcs+5kmDNOTSTtnS7buL/u1CKoKiV82vydx0\nbofipCvwG58Rj+BWfclusgQLITdmu34z35Kc2wIDAQABAoIBAHlHKOzupfTEAj95\njBy4l4SzK4jMofPF5fbA0NGdk92/p9z/RaO+X3Y31XdEUhZfAh2QCs8f25urE+wR\nl7WhszgU6LOkF9E8Xw89FqzHi3LCxQTiLzyNqLMKe2tTOOb4SU+qy9ofOdW+7xR8\nU5MP0XSCvvF8d0+vKzGBoWRUMcukHgVAs+sZ6NyPXN2UoJ9jvuGTpQSstXurX0Ek\nKMP0fyz22m6M31KDSkD79b3IxueLjSx3JBcNHox8XLdc/5YDMc8VMp3aBUeol0Xa\nZRPkmikXLGTHcJZjrjROpnPIF1B+kTDVsZNtbd84Pn3E8/HwikT5bt0her0aiB0b\nvivlDikCgYEA8ct9GOrEZyOTXRMJWGpHW5tsI6d8tFGNDYHF0fYdMii/17R0ytxn\nmXnOc9FYMpmXCyzjqumYzFJgc5LCMsBaGRaV8rPkASPfLPk6JzL+4plFew1HSw+9\n9UPQjynsYBctl1ef6gvFMC/zJQUJ42s0Y9t/+MoEekMOqKpO5PPz8gUCgYEA0lIW\nsHTv+s9DbACmHIYiQdDEAvgeGw6RHX0yqYpMnEPomMUMsI5EKufHnjuR0VcNhl4d\nWE+9QRGKRG8YeIqVyYSGTxAljXOnj1Q49Q72DhpbTIHlHEgmAlLkYIa1tJ4DzSFG\nHblDxFHzvs9V4mA/vUnb2NHGZ6PlIX+CtSJ1KV8CgYEA7AVZ40ym0pajbiL66Fc1\nuHIKKPOAgvNn4Ftgoga/kQq92OzJZIuohOOlZuBeW2YZTktPILJM+IUgqTAEaE3i\npMKrM/HtCj/dxaSx4zmgG8jJTcg0Y0zGe/bqShT+Kv30/toFuwwqO1NS4Dv+3wLy\nbNcCH/PyUvXKBVHZGRwYb5ECgYEArw7ejc83dCaR8tJzcOiAmRGAJQyKWnD8fnQX\n+CAB9ktbzdSt5EL2IFQ9xcnFbF4uBrpNaJUubHuB/8YMs0B+vnYNKL/C0gMC4/zx\nT6A9U63CcmLn5Wt0H5kJOALIOWcQuOvKJbFv43dnD1oaHUuJoi9YyxaIMvmrHP+6\nNrRQmrcCgYBqg+swcahNhPUT4bKXgn6Pd7ow5L7Z39oo/L4Ser6HWxk/7DXdd7oN\n3pF+ghQeBR4qtAiDPMjE86+5lRhmfoox1Rlcjl13H4gYegRvpyo6n3vTFC4NeuBm\nywcgknSgQP0N+YGyWTCB4qe4GimS/E5tqWLN3Z8zT6AID9oTR7BgXg==\n-----END RSA PRIVATE KEY-----\n",
          "validator-username": "cloudtest-validator",
          "chef-server-url": "https://api.opscode.com/organizations/cloudtest"
        });
    }
    response.deployment = deployment;
    return response;
  };

  $scope.edit = function() {
    var response = $scope.prepDeployment();
    DeploymentData.set(response.deployment);
    $location.path('/blueprints/design');
  };

  $scope.submit = function(action) {
    if ($scope.submitting === true)
      return;
    $scope.submitting = true;

    var response = $scope.prepDeployment(action);
    if (response.break_flag){
      $scope.submitting = false;
      _.each(response.errors, function(error) {
        $scope.notify(error);
      })
      return;
    }

    if ($scope.auth.identity.loggedIn) {
      response.deployment.$save(function(returned, getHeaders){
        if (action == '+preview') {
          workflow.preview = returned;
          $location.path('/' + $scope.auth.context.tenantId + '/workflows/+preview');
        } else {
          var deploymentId = getHeaders('location').split('/')[3];
          console.log("Posted deployment", deploymentId);
          $location.path(getHeaders('location'));
        }
      }, function(error) {
        console.log("Error " + error.data + "(" + error.status + ") creating new deployment.");
        console.log(response.deployment);
        var info = {data: error.data, status: error.status, title: "Error Creating Deployment",
                    message: "There was an error creating your deployment:"};
        $scope.open_modal('/partials/app/_error.html', {error: info});
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
    $scope.updateRegions();
  };
  $scope.$on('logIn', $scope.OnLogIn);
}

//Handles an existing deployment
function SecretsController($scope, $location, $resource, $routeParams, $modalInstance) {
  $scope.load = function() {
    console.log("Starting load");
    $scope.loading = { secrets: true };
    this.klass = $resource((checkmate_server_base || '') + $location.path() + '/secrets.json');
    $scope.secrets_info = this.klass.get($routeParams, function(data, getResponseHeaders){
      $scope.loading.secrets = false;
      angular.forEach(data.secrets, function(s) {
        if (s.status == 'LOCKED')
          $scope.secrets_dismissed = true;
      });
    });
  };

  $scope.close = function(response) {
    return $modalInstance.close(response);
  }

  $scope.dismiss = function(response) {
    return $modalInstance.dismiss(response);
  }

  $scope.secrests_dismissed = false;
  $scope.dismissSecrets = function() {
    $scope.secrets_dismissed = true;
    angular.forEach($scope.secrets_info.secrets, function(element) {
      element.status = 'LOCKED';
    });
    $scope.secrets_info.$save();
  };

  $scope.allAvailableSecrets = function() {
    var result = '';
    _.each($scope.secrets_info.secrets, function(element, key) {
      if (element.status == 'AVAILABLE')
        result = result + key + ': ' + element.value + '\n';
    });
    return result;
  };

  $scope.load();
}

//Handles an existing deployment
function DeploymentController($scope, $location, $resource, $routeParams, $modal, deploymentDataParser, $http, urlBuilder, Deployment, workflow, DeploymentTree) {
  //Model: UI
  $scope.showSummaries = true;
  $scope.showStatus = false;
  $scope.showAdvancedDetails = false;
  $scope.showInstructions = false;
  $scope.auto_refresh = true;
  $scope.showCommands = false;

  $scope.name = 'Deployment';
  $scope.data = {};
  $scope.data_json = "";

  $scope.tree = { selected_nodes: {}, count: 0 };
  $scope.toggle_selected_node = function(node) {
    var services = $scope.available_services($scope.data);
    if (services.indexOf(node.component) == -1)
      return false;

    if (node.id in $scope.tree.selected_nodes) {
      $scope.tree.count--;
      delete $scope.tree.selected_nodes[node.id];
    } else {
      $scope.tree.count++;
      $scope.tree.selected_nodes[node.id] = node;
    }

    return true;
  }

  $scope.get_blueprint_url = function(deployment) {
    if (!(deployment && deployment.environment && deployment.environment.providers))
      return "";

    var all_providers = deployment.environment.providers;
    var providers = _.find(all_providers, function(p) { return p.constraints; }) || {};
    var constraint = _.find(providers.constraints, function(c) { return c.source; }) || {};
    var original_url = constraint.source;
    if (!original_url)
      return "";

    var last_hash = original_url.lastIndexOf('#')
    if (last_hash == -1) last_hash = original_url.length;
    var repo_url = original_url.substring(0,last_hash);
    var branch_url = original_url.substring(last_hash, original_url.length);
    var url = repo_url.replace("git://", "http://").replace(/\.git$/, "") + branch_url;

    return url;
  }

  $scope.display_details = function(details) {
    var available_details = false;
    angular.forEach(details, function(detail) {
      if (!detail['is-secret']) {
        available_details = true;
      }
    });
    return available_details;
  }

  $scope.loading = {};
  $scope.check = function(deployment) {
    var _group_messages = function(resources) {
      var messages = {};
      messages.has_errors = false;
      angular.forEach(resources, function(info_list, id) {
        var has_messages = false;
        messages[id] = {
          error: [],
          warning: [],
          info: []
        };
        angular.forEach(info_list, function(info) {
          messages.has_errors = has_messages = true;
          var type = info.type.toLowerCase();
          if (type == 'information') type = 'info';
          messages[id][type].push(info.message);
        });
        if (!has_messages)
          messages[id].success = true;
      });
      return messages;
    };

    $scope.loading.check = true;
    $scope.resources_info = {};
    Deployment.check(deployment).then(
      function success(response) {
        $scope.loading.check = false;
        $scope.resources_info = _group_messages(response.data.resources);
      },
      function error(response) {
        $scope.loading.check = false;
        $scope.resources_info.has_errors = true;
        $scope.resources_info.error = response;
      }
    );
  }

  $scope.showSecrets = function() {
    if ($scope.data.secrets != 'AVAILABLE') return;

    var options = {
      templateUrl: '/partials/deployments/_secrets.html',
      controller: 'SecretsController',
    };
    $modal.open(options);
  };

  $scope.shouldDisplayWorkflowStatus = function() {
    var operation = $scope.data.operation;
    if(operation && operation.status && operation.link){
      var is_workflow_operation = operation.link.split('/').indexOf('workflows') !== -1;
      return (operation.status == 'NEW' || operation.status == 'IN PROGRESS' || operation.status == 'PAUSED') && is_workflow_operation;
    } else {
      return false;
    }
  }

  $scope.urlBuilder = urlBuilder;

  // Called by load to refresh the status page
  $scope.reload = function(original_url) {
    // Check that we are still on the same page, otherwise don't reload
    if ($location.url() == original_url && $scope.auto_refresh !== false)
      $scope.load();
  };

  $scope.delayed_refresh = function() {
    var original_url = $location.url();
    setTimeout(function() {$scope.reload(original_url);}, 5000);
  };

  $scope.toggle_auto_refresh = function() {
    $scope.auto_refresh = !$scope.auto_refresh;
    $scope.delayed_refresh();
  };

  $scope.load_workflow_stats = function(operation){
    if(!operation || (operation.link && !(operation.link.indexOf('canvases') === -1)) || !operation.link)
      return null;

    var workflows = $resource((checkmate_server_base || '') + operation.link + '.json')
    workflows.get({}, function(data, getResponseHeaders){
      var tasks = workflow.flattenTasks({}, data.task_tree);
      var all_items = workflow.parseTasks(tasks, data.wf_spec.task_specs);
      $scope.count = all_items.length;
      var statistics = workflow.calculateStatistics(all_items);
      $scope.totalTime = statistics.totalTime;
      $scope.timeRemaining = statistics.timeRemaining;
      $scope.taskStates = statistics.taskStates;
      $scope.percentComplete = (($scope.totalTime - $scope.timeRemaining) / $scope.totalTime) * 100;
    })
  };

  $scope.group_resources = function(resources) {
    var groups = {};

    angular.forEach(resources, function(r) {
      var name = r['dns-name'];
      if (!groups[name]) groups[name] = [];

      groups[name].push(r);
    });

    return groups;
  }

  $scope.load = function() {
    console.log("Starting load");
    this.klass = $resource((checkmate_server_base || '') + $location.path() + '.json');
    this.klass.get($routeParams, function(data, getResponseHeaders){
      $scope.data_json = JSON.stringify(data, null, 2);

      $scope.load_workflow_stats(data.operation);
      data.display_status = Deployment.status(data);
      $scope.data = data;
      if (data['operations-history'])
        $scope.operations_history = angular.copy(data['operations-history']).reverse();
      $scope.resources = _.values($scope.data.resources);
      $scope.resource_groups = $scope.group_resources($scope.resources);
      $scope.showCommands = $scope.auth.is_current_tenant($scope.data.tenantId);
      $scope.abs_url = $location.absUrl();
      $scope.clippy_element = "#deployment_summary_clipping";
      try {
        $scope.formatted_data = deploymentDataParser.formatData(data);
      } catch(err) {
        console.log('Could not format deployment data');
        $scope.formatted_data = {};
      }

      if ($scope.data.operation !== undefined && $scope.data.operation.status != 'COMPLETE') {
        $scope.delayed_refresh();
      }

    });
  };

  $scope.available_services = function(deployment) {
    return Deployment.available_services(deployment);
  }

  $scope.is_scalable_service = function(resource, deployment) {
    if (!deployment)
      deployment = $scope.data;

    var service = resource.service;
    if (!service) return false;

    var is_available = ($scope.available_services(deployment).indexOf(service) > -1);
    var is_main_instance = deployment.plan.services[service].component.instances.indexOf(resource.index) > -1;
    return is_available && is_main_instance;
  }

  $scope.add_nodes = function(deployment, service, num_nodes) {
    Deployment.add_nodes(deployment, service, num_nodes)
      .then($scope.load, $scope.show_error);
  };

  $scope.delete_nodes = function(deployment, resources_map) {
    var selected_resources = [];
    var service_name;
    var num_nodes = 0;
    for (id in resources_map) {
      var resource = resources_map[id];
      if (resource) {
        num_nodes++;
        selected_resources.push(deployment.resources[id]);
        service_name = deployment.resources[id].service;
      }
    }
    Deployment.delete_nodes(deployment, service_name, num_nodes, selected_resources)
      .then($scope.load, $scope.show_error);
  };

  $scope.take_offline = function(deployment, resource) {
    var application = Deployment.get_application(deployment, resource);
    var resource_name = application['dns-name'];
    Deployment.take_offline(deployment, application).then(
      function success(response) {
        $scope.notify(resource_name + ' will be taken offline');
        $scope.load();
      },
      $scope.show_error
    );
  }

  $scope.bring_online = function(deployment, resource) {
    var application = Deployment.get_application(deployment, resource);
    var resource_name = application['dns-name'];
    Deployment.bring_online(deployment, application).then(
      function success(response) {
        $scope.notify(resource_name + ' will be online shortly');
        $scope.load();
      },
      $scope.show_error
    );
  }

  $scope.display_progress_bar = function() {
    return ($scope.data.operation && $scope.data.operation.status != 'COMPLETE');
  };

  $scope.display_workflow = function() {
    try {
      return ($scope.data.operation.link.indexOf('workflow') > -1);
    } catch(err) {
      return false;
    }
  };

  $scope.operation_progress = function() {
    var percentage = 0;
    if ($scope.data.operation) {
      percentage = Math.round( ($scope.data.operation.complete / $scope.data.operation.tasks) * 100 );
    }

    return percentage;
  };

  $scope.is_resumable = function() {
    return $scope.data.operation && $scope.data.operation.resumable;
  }

  $scope.is_retriable = function() {
    return $scope.data.operation && $scope.data.operation.retriable;
  }

  $scope.retry = function() {
    var url = $scope.data.operation['retry-link'];
    $http.post(url);
  }

  $scope.resume = function() {
    var url = $scope.data.operation['resume-link'];
    $http.post(url);
  }

  $scope.save = function() {
    var editor = _.find($('.CodeMirror'), function(c) {
      return c.CodeMirror.getTextArea().id == 'source';
      });

    if ($scope.auth.is_logged_in()) {
      var klass = $resource((checkmate_server_base || '') + '/:tenantId/deployments/:id/.json', null, {'get': {method:'GET'}, 'save': {method:'PUT'}});
      var thang = new klass(JSON.parse(editor.CodeMirror.getValue()));
      thang.$save($routeParams, function(returned, getHeaders){
          // Update model
          $scope.data = returned;
          $scope.data_json = JSON.stringify(returned, null, 2);
          $scope.notify('Saved');
        }, function(error) {
          var info = {data: error.data, status: error.status, title: "Error Saving",
                      message: "There was an error saving your JSON:"};
          $scope.open_modal('/partials/app/_error.html', {error: info});
        });
    } else {
      $scope.loginPrompt().then($scope.save);
    }
  };

  $scope.delete_deployment = function(force) {
    var retry = function() {
      $scope.delete_deployment(force);
    };

    if ($scope.auth.is_logged_in()) {
      var klass = $resource((checkmate_server_base || '') + '/:tenantId/deployments/:id/.json', null, {'save': {method:'PUT'}});
      var thang = new klass();
      var params = jQuery.extend({}, $routeParams);
      if (typeof(force) !== undefined)
        params.force = force;
      thang.$delete(params, function(returned, getHeaders){
          // Update model
          $scope.data = returned;
          $scope.data_json = JSON.stringify(returned, null, 2);
          $scope.notify('Deleting deployment');
          $scope.delayed_refresh();
        }, function(error) {
          var info = {data: error.data, status: error.status, title: "Error Deleting",
                      message: "There was an error deleting your deployment"};
          $scope.open_modal('/partials/app/_error.html', {error: info});
        });
    } else {
      $scope.loginPrompt().then(retry);
    }
  };

  $scope.sync_success = function(response){
    $scope.load();
    if (response)
        $scope.notify(response.data.length + ' resources synced');
  }

  $scope.sync_failure = function(error){
    var info = {data: error.data, status: error.status, title: "Error Syncing",
                message: "There was an error syncing your deployment"};
    $scope.open_modal('/partials/app/_error.html', {error: info});
  }

  // This also exists on DeploymentListController - can be refactored
  $scope.sync = function() {
    if ($scope.auth.is_logged_in()) {
      Deployment.sync($scope.data).then($scope.sync_success, $scope.sync_failure)
    } else {
      $scope.loginPrompt().then($scope.sync);
    }
  };

  $scope.tree_data = null;
  $scope.$watch('data', function(newData, oldData) {
    $scope.tree_data = DeploymentTree.build(newData);
  });
}

/*
 * Admin controllers
 */
function FeedbackListController($scope, $location, $resource, items, scroll) {
  //Model: UI
  $scope.showSummaries = true;
  $scope.showStatus = false;

  $scope.name = 'Feedback';

  $scope.load = function() {
    console.log("Starting load");
    this.klass = $resource((checkmate_server_base || '') + '/admin/feedback/.json');
    this.klass.get({}, function(list, getResponseHeaders){
      console.log("Load returned");
      var received_items = items.receive(list, function(item, key) {
        item.id = key;
        if ('feedback' in item)
          item.received = item.feedback.received;
        return item;});
      $scope.count = received_items.count;
      $scope.items = received_items.all;
      console.log("Done loading");
    },
    function(response) {
      $scope.show_error(response);
    });
  };

  //Setup
  $scope.load();
}

/*
 * Provider controllers
 */
function ProviderListController($scope, $location, $resource, items, scroll) {
  //Model: UI
  $scope.name = 'Providers';
  $scope.load = function() {
    console.log("Starting load");
    this.klass = $resource((checkmate_server_base || '') + '/:tenantId/providers/.json');
    this.klass.get({tenantId: $scope.auth.context.tenantId}, function(list, getResponseHeaders){
      console.log("Load returned");
      var received_items = items.receive(list, function(item, key) {
        return {id: key, name: item.name, vendor: item.vendor};});
      $scope.count = received_items.count;
      $scope.items = received_items.all;
      console.log("Done loading");
    });
  };

  $scope.load();
}

/*
 * Environment controllers
 */
function EnvironmentListController($scope, $location, $resource, items, scroll) {
  //Model: UI
  $scope.showSummaries = true;
  $scope.showStatus = false;

  $scope.name = 'Environments';

  $scope.load = function() {
    console.log("Starting load");
    this.klass = $resource((checkmate_server_base || '') + '/:tenantId/environments/.json');
    this.klass.get({tenantId: $scope.auth.context.tenantId}, function(list, getResponseHeaders){
      console.log("Load returned");
      var received_items = items.receive(list, function(item, key) {
        return {id: key, name: item.name, vendor: item.vendor, providers: item.providers};});
      $scope.count = received_items.count;
      $scope.items = received_items.all;
      console.log("Done loading");
    });
  };

  //Setup
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

function ResourcesController($scope, $resource, $location, Deployment, $http, $q){
  $scope.deployment = {};
  $scope.selected_resources = [];
  $scope.resources_by_provider = {};
  $scope.error_msgs = {};
  $scope.loading_status = {
    nova: false,
    'load-balancer': false,
    database: false
  };

  $scope.add_to_deployment = function(decorated_resource){
    var resource_list = $scope.resources_by_provider[decorated_resource.object.provider];
    $scope.selected_resources.push(decorated_resource);
    resource_list.splice(resource_list.indexOf(decorated_resource), 1);
  };

  $scope.remove_from_deployment = function(decorated_resource){
    $scope.resources_by_provider[decorated_resource.object.provider].push(decorated_resource);
    $scope.selected_resources.splice($scope.selected_resources.indexOf(decorated_resource), 1);
  };

  $scope.get_checkmate_resources = function(instance_ids, provider, type){
    var tenant_id = $scope.auth.context.tenantId;
    var url = '/'+tenant_id+'/resources';
    var params = {};
    if (instance_ids)
      params.id = instance_ids
    if (provider)
      params.provider = provider
    if (type)
      params.type = type

    var config = { params: params };
    return $http.get(url, config);
  };

  var filter_local_resources = function(resource_ids, resource_type) {
    return $scope.get_checkmate_resources(resource_ids, resource_type).then(
      function(response) {
        var cm_resources = response.data.results;
        var all_resources = $scope.resources_by_provider[resource_type];
        exclude_resources_in_checkmate(all_resources, cm_resources);
      }
    );
  }

  var wrap_and_filter_resources = function(resources, resource_type, filter_local_resources) {
    var deferred = $q.defer();
    var promise = deferred.promise;
    var resource_ids = [];

    $scope.resources_by_provider[resource_type] = [];
    angular.forEach(resources, function(resource){
      $scope.resources_by_provider[resource_type].push(decorate_resource(resource))
      resource_ids.push(resource.instance.id);
    });
    if (filter_local_resources) {
      promise = filter_local_resources(resource_ids, resource_type);
    } else {
      deferred.resolve();
    }

    return promise;
  }

  $scope.get_resources = function(resource_type, filter_local_resources){
    delete $scope.error_msgs[resource_type];
    var tenant_id = $scope.auth.context.tenantId;
    if ($scope.auth.identity.loggedIn && tenant_id){
      var url = '/:tenantId/providers/rackspace.'+resource_type+'/resources';
      var server_api = $resource((checkmate_server_base || '') + url, {tenantId: $scope.auth.context.tenantId});
      $scope.loading_status[resource_type] = true;
      server_api.query(
        function(response) {
          var resources = response;
          wrap_and_filter_resources(resources, resource_type, filter_local_resources).then(function() {
            $scope.loading_status[resource_type] = false;
          });
        },
        function(response) {
          $scope.error_msgs[resource_type] = "Error loading "+resource_type+" list";
          $scope.loading_status[resource_type] = false;
        }
      );
    }
  };

  var exclude_resources_in_checkmate = function(all_resources, checkmate_resources) {
    var not_in_checkmate;
    for (var id in checkmate_resources) {
      var checkmate_resource = checkmate_resources[id];
      for (var key in checkmate_resource) {
        var attr = checkmate_resource[key];
        if (typeof(attr) == 'string') continue;
        var existing_id = attr.instance.id;
        angular.forEach(all_resources, function(resource) {
          if (resource.instance_id == existing_id)
            resource.in_checkmate = true;
        });
      }
    }
  }

  var decorate_resource = function(resource) {
    return {
      object: resource,
      instance_id: resource.instance.id,
      in_checkmate: false
    };
  }

  $scope.load_resources = function(){
    $scope.get_resources('nova');
    $scope.get_resources('load-balancer');
    $scope.get_resources('database');
  }

  $scope.get_new_deployment = function(tenant_id){
    var url = '/:tenantId/deployments';
    DeploymentResource = $resource((checkmate_server_base || '') + url, {tenantId: tenant_id});
    return new DeploymentResource({});
  }

  $scope.sync_success = function(returned, getHeaders){
    if (returned !== undefined)
      $scope.notify(Object.keys(returned).length + ' resources synced');
  }

  $scope.sync_failure = function(error){
    var info = {data: error.data, status: error.status, title: "Error Syncing",
                message: "There was an error syncing your deployment"};
    $scope.open_modal('/partials/app/_error.html', {error: info});
  }

  $scope.submit = function(){
    var url = '/:tenantId/deployments',
        tenant_id = $scope.auth.context.tenantId,
        deployment = $scope.get_new_deployment(tenant_id),
        DEFAULT_TATTOO = 'http://7555e8905adb704bd73e-744765205721eed93c384dae790e86aa.r66.cf2.rackcdn.com/custom-tattoo.png',
        DEFAULT_20_BY_20 = 'http://7555e8905adb704bd73e-744765205721eed93c384dae790e86aa.r66.cf2.rackcdn.com/custom-20x20.png';

    deployment.inputs = {custom_resources: []};
    for (i=0; i<$scope.selected_resources.length; i++){
      deployment.inputs.custom_resources.push($scope.selected_resources[i].object)
    }
    deployment.blueprint = {
      'services': {},
      'name': $scope.deployment.name,
      'meta-data': {
        'application-name': 'Custom',
        'reach-info': {
          'tattoo': DEFAULT_TATTOO,
          'icon-20x20': DEFAULT_20_BY_20
        }
      }
    };
    deployment.environment = { //TODO Make providers list dynamic based on resources
        "description": "This environment uses next-gen cloud servers.",
        "name": "Next-Gen Open Cloud",
        "providers": {
            "nova": {},
            "block": {},
            'database': {},
            'load-balancer': {},
            "common": {
                "vendor": "rackspace"
            }
        }
    };
    deployment.status = 'NEW';
    deployment.name = $scope.deployment.name;
    deployment.$save(function(result, getHeaders){
      console.log("Posted deployment");
      Deployment.sync(deployment, $scope.sync_success, $scope.sync_failure)
      $location.path('/' + tenant_id + '/deployments/' + result['id']);
    }, function(error){
      console.log("Error " + error.data + "(" + error.status + ") creating new deployment.");
      console.log(deployment);
    });
  };
}

function BlueprintNewController($scope, $location, BlueprintHint, Deployment, DeploymentTree, BlueprintDocs, DelayedRefresh, github, options, $location, $resource, workflow) {
  $scope.deployment = {
    "blueprint": {"name": "your blueprint name"},
    "inputs": {},
    "environment": {},
    "name": {}
  };
  $scope.deployment_string = jsyaml.safeDump($scope.deployment, null, 2);
  $scope.parsed_deployment_tree = DeploymentTree.build({});
  $scope.errors = {};

  var _to_yaml = function() {
    $scope.deployment_string = jsyaml.safeDump(JSON.parse($scope.deployment_string));
    $scope.codemirror_options.lint = false;
    $scope.codemirror_options.mode = 'text/x-yaml';
    $scope.foldFunc = CodeMirror.newFoldFunction(CodeMirror.fold.indent);
  }

  var _to_json = function() {
    $scope.deployment_string = JSON.stringify(jsyaml.safeLoad($scope.deployment_string), null, 2);
    $scope.codemirror_options.lint = true;
    $scope.codemirror_options.mode = 'application/json';
    $scope.foldFunc= CodeMirror.newFoldFunction(CodeMirror.fold.brace);
  }

  $scope.toggle_editor_type = function() {
    var current_mode = $scope.codemirror_options.mode;

    try {
      if ($scope.codemirror_options.mode == 'application/json') {
        _to_yaml();
      } else {
        _to_json();
      }
    } catch(err) {
      $scope.show_error(err);
    }
  }

  $scope.load_blueprint = function() {
    var url = $location.search().url;
    if (url) {
      var remote = github.parse_url(url);
      github.get_blueprint(remote).then(
        function(blueprint) {
          $scope.deployment_string = jsyaml.safeDump(blueprint);
        },
        function(response) {
          console.log(response);
        }
      );
    }
  }

  $scope.parse_deployment = function(newValue, oldValue) {
    var parse_func = ($scope.codemirror_options.mode == 'application/json') ? JSON.parse : jsyaml.safeLoad;
    try {
      $scope.deployment = parse_func(newValue);
    } catch(err) {
      console.log("Invalid JSON/YAML. Will not try to parse deployment.")
      return;
    }

    Deployment.parse($scope.deployment, $scope.auth.context.tenantId, function(response) {
      $scope.parsed_deployment_tree = DeploymentTree.build(response);
    })
  };

  $scope.delayed_parse_deployment = DelayedRefresh.get_instance();
  $scope.refresh_parse_deployment = function(newValue, oldValue) {
    console.log("Refreshing...");
    $scope.delayed_parse_deployment.refresh(
      function () {
        $scope.parse_deployment(newValue, oldValue);
      }
    );
  };

  $scope.submit = function(action){
    if ($scope.submitting === true)
      return;
    $scope.submitting = true;

    var deployment_obj;
    try {
      deployment_obj = jsyaml.safeLoad($scope.deployment_string);
    } catch(err) {
      $scope.show_error(err);
      console.log('Could not parse the blueprint');
      $scope.submitting = false;
      return;
    }

    // Temp hack to set chef server credentials
    if (deployment_obj.environment && deployment_obj.environment.providers && deployment_obj.environment.providers['chef-server']) {
      if (!deployment_obj.inputs) {
        deployment_obj.inputs = {};
      };
      if (!deployment_obj.inputs.blueprint) {
        deployment_obj.inputs.blueprint = {};
      };
      _.extend(deployment_obj.inputs.blueprint,
        {
          "chef-server-user-key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEpQIBAAKCAQEAuWhEX/K00A7Phuxcz6ltb412hnxiocAoV4CzFwDpk6JsIGAK\nUCc0Uc6UR/cZ8tMOsggST2InnOJiuwB4aNpdJi6JIXNh0Q1PtlDr8WlSDPESB5Ms\nZf1zud/23d/jKdPeYhnQzmjcdzhxbiPPbBO1U3ZrAy03d17RszGDjHvsOYyMdP8U\nbZanujE8078in2ph4A9fZb7QwiiqHgHG8f6M7CttJJ/HEAR32w4ElMgIN8JJegTS\n17EK6o3euAcdVN5r7LkjYDy6fFR1sHLE1Y+7svcCmZT2CJkfxjKlTt9w1ZGd2lAN\n1wfCqj7nM3ImxfbNAhnMByGCo5XHuMDhKvJ3rQIDAQABAoIBAQCq5O95HOYKjEw+\nyeh2RG2pj9O6/DWRb+P/W5I3VtD1EpXldYCsBqbT7LyCZMHXLzDxaj0uTIPEuGpW\ngYV66CNJyUT+vzJfFYzuuEHx/6jwYtfCgaY/z9D2d/g85FunNzFYbQEo8ECd5zmu\nUnWi4buV1aWnhOsGLTDOoYnmWGcRVuhXYxvGsJiFOIbLuEfcaYPdYnTmpGZ5NLJd\n2SAs/KWgIumRNh2bL8rjFTGH8z5DSt4bhizxdzC6SqouDwVPcWYUuT6cNYOxi5TK\ndEiOEJpXAO9TUqUfE5R3p2e64bezbF8nFYbAbwadOSIca2bhJAJX+/H5Vl3Ml8zG\nb/Um0a3hAoGBAOF5aHf+w842+zNzcpntnGW7boY/A0utz3Jed/tdaWD+bRPXR3Eb\n5Kqk/rRMInRwV7bBO4zQ9IhwEHmIhsDsqZ+gXmFN3+plQ18H/AELVPMb5vjAj/0s\nqFgMX+BZv+DA5K29hxJ4lqaRKGZr8cNHKi2vZIuGesBoNwW8NAc1P5/FAoGBANKC\nMx74XAe8fq3Ba0X7hqAsE8RGXxyMc07m4YqPz8Ib12NBqIFYKbFOFHs0btBf7P5P\n/WB0m6xoCl4eLQq6SIPNy9DeXfLzczqUGbRMg+t7iC6dZXE1cUNbkpFHc5KnD7rZ\nLLfB33Kx0KtQHf3KmntCJ0pSE0Hh6MxGcqvZEE7JAoGBAN1V3xWcQ/6Uvnc9Z0xv\nkk3TdqXWCZgq4S92SPW6Nw399Hm7pOgF560UFuxKqLAA8Dn46kpLfSDKUYHcYdvU\n9pY6SSvf1GU2TrJlFh64TwXvaAbckPyI8CCu1RdZQyCQemuLV6LsOYb9i9kvMb7u\nhxsdx+endayXIRxCKhjBTtm5AoGBANBlIpSjTABAo6wB0d/bDECewgbJn7jUdgaD\nXH5etk80XrsdMeKyU7v6Tx5VHurcO/LbXzvQ1JgN+02HVBHNrqIE5qPkr18nkUhJ\ne1TZdrN1fLChEt7LCFClY+i8snZZOqJAAxv7KukRjUE7NCWeH+ar69eQfw32xg8M\nItNrNNC5AoGALMFodBcRLEsfHunzsBe66F2mnx8qO9HoTYuJcBCdvz0DYxvXHS60\nRAu3iCOwMMIiUZkc1/xize0aCNvxaLZO5hduLhLSSZfjC1HXFx9HQKcbEXIk+K0A\nTgIT2DvqGKO2EYLiErkWHN7LVkyt9qZJ4m1tFfwlfG2jTUoYB9maZRw=\n-----END RSA PRIVATE KEY-----\n",
          "chef-server-username": "ziadsawalha",
          "validator-pem": "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEAxqZ1OqmpU2AQMnFCToLLW23J9dPvCNJ81XaM3c3PEyJS9rkx\n2u29oOEWjEybwBn0UgoMMJEhK/4G1zVG176xNEsr6iYQ6aOs3x7R3IeRP5fwBxwY\nbuZonZ8vTQuZ+ZIrawy10XqYrlgb6w+oKTnzwYDWfwBU13UZjXA5d/8RECYrfojS\nNWRXI3k1H6WXjb9l2x/IFcjt+WmQeA23tBFnFuPF1Gn3vkzFXKRJH/cKS6eCigoy\nl2RA+7IDMPMmATCE4T3VO5Rplr0OYcs+5kmDNOTSTtnS7buL/u1CKoKiV82vydx0\nbofipCvwG58Rj+BWfclusgQLITdmu34z35Kc2wIDAQABAoIBAHlHKOzupfTEAj95\njBy4l4SzK4jMofPF5fbA0NGdk92/p9z/RaO+X3Y31XdEUhZfAh2QCs8f25urE+wR\nl7WhszgU6LOkF9E8Xw89FqzHi3LCxQTiLzyNqLMKe2tTOOb4SU+qy9ofOdW+7xR8\nU5MP0XSCvvF8d0+vKzGBoWRUMcukHgVAs+sZ6NyPXN2UoJ9jvuGTpQSstXurX0Ek\nKMP0fyz22m6M31KDSkD79b3IxueLjSx3JBcNHox8XLdc/5YDMc8VMp3aBUeol0Xa\nZRPkmikXLGTHcJZjrjROpnPIF1B+kTDVsZNtbd84Pn3E8/HwikT5bt0her0aiB0b\nvivlDikCgYEA8ct9GOrEZyOTXRMJWGpHW5tsI6d8tFGNDYHF0fYdMii/17R0ytxn\nmXnOc9FYMpmXCyzjqumYzFJgc5LCMsBaGRaV8rPkASPfLPk6JzL+4plFew1HSw+9\n9UPQjynsYBctl1ef6gvFMC/zJQUJ42s0Y9t/+MoEekMOqKpO5PPz8gUCgYEA0lIW\nsHTv+s9DbACmHIYiQdDEAvgeGw6RHX0yqYpMnEPomMUMsI5EKufHnjuR0VcNhl4d\nWE+9QRGKRG8YeIqVyYSGTxAljXOnj1Q49Q72DhpbTIHlHEgmAlLkYIa1tJ4DzSFG\nHblDxFHzvs9V4mA/vUnb2NHGZ6PlIX+CtSJ1KV8CgYEA7AVZ40ym0pajbiL66Fc1\nuHIKKPOAgvNn4Ftgoga/kQq92OzJZIuohOOlZuBeW2YZTktPILJM+IUgqTAEaE3i\npMKrM/HtCj/dxaSx4zmgG8jJTcg0Y0zGe/bqShT+Kv30/toFuwwqO1NS4Dv+3wLy\nbNcCH/PyUvXKBVHZGRwYb5ECgYEArw7ejc83dCaR8tJzcOiAmRGAJQyKWnD8fnQX\n+CAB9ktbzdSt5EL2IFQ9xcnFbF4uBrpNaJUubHuB/8YMs0B+vnYNKL/C0gMC4/zx\nT6A9U63CcmLn5Wt0H5kJOALIOWcQuOvKJbFv43dnD1oaHUuJoi9YyxaIMvmrHP+6\nNrRQmrcCgYBqg+swcahNhPUT4bKXgn6Pd7ow5L7Z39oo/L4Ser6HWxk/7DXdd7oN\n3pF+ghQeBR4qtAiDPMjE86+5lRhmfoox1Rlcjl13H4gYegRvpyo6n3vTFC4NeuBm\nywcgknSgQP0N+YGyWTCB4qe4GimS/E5tqWLN3Z8zT6AID9oTR7BgXg==\n-----END RSA PRIVATE KEY-----\n",
          "validator-username": "cloudtest-validator",
          "chef-server-url": "https://api.opscode.com/organizations/cloudtest"
        });
    }

    var url = '/:tenantId/deployments';
    if (action)
      url += '/' + action;

    var Dep = $resource((checkmate_server_base || '') + url, {tenantId: $scope.auth.context.tenantId});
    var deployment = new Dep(deployment_obj);

    deployment.$save(
      function success(returned, getHeaders){
        if (action == '+preview') {
          workflow.preview = returned;
          $location.path('/' + $scope.auth.context.tenantId + '/workflows/+preview');
        } else {
          var deploymentId = getHeaders('location').split('/')[3];
          console.log("Posted deployment", deploymentId);
          $location.path(getHeaders('location'));
        }
      },
      function error(error) {
        $scope.show_error(error);
        $scope.submitting = false;
      }
    );
  }

  $scope.newBlueprintCodemirrorLoaded = function(_editor){
    $scope.inputs = {};
    CodeMirror.commands.autocomplete = function(cm) {
      CodeMirror.showHint(cm, BlueprintHint.hinting);
    };

    function betterTab(cm) {
      if (cm.somethingSelected()) {
        cm.indentSelection("add");
      } else {
        cm.replaceSelection(cm.getOption("indentWithTabs")? "\t":
                            Array(cm.getOption("indentUnit") + 1).join(" "), "end", "+input");
      }
    }

    _editor.setOption('extraKeys', {
      'Ctrl-Space': 'autocomplete',
      Tab: betterTab
    })

    var _update_options = function() {
      var blueprint;
      try {
        blueprint = jsyaml.safeLoad($scope.deployment_string);
      } catch(err) {
        blueprint = {};
        console.log('Could not parse blueprint');
      }
      var inner_blueprint = blueprint.blueprint || {};
      var opts = options.getOptionsFromBlueprint(inner_blueprint) || {};
      $scope.options_to_display = opts.options_to_display || [];
      $scope.option_groups = opts.groups || {};
      $scope.option_headers = opts.option_headers || {};
      $scope.$$phase || $scope.$apply();
    }
    var _delayed_refresh_options = DelayedRefresh.get_instance(_update_options);

    _editor.on('change', function() {
      _delayed_refresh_options.refresh();
    });

    _editor.on('cursorActivity', function(instance, event) {
      var path_tree = BlueprintHint.get_fold_tree(_editor, _editor.getCursor());
      var doc = BlueprintDocs.find(path_tree);
      $scope.help_display = doc.text();
      $scope.$$phase || $scope.$apply();
    });
    $scope.$watch('codemirror_options.onGutterClick', function(newValue, oldValue) {
      _editor.off('gutterClick', oldValue);
      _editor.on('gutterClick', newValue);
    });
  }

  $scope.foldFunc = CodeMirror.newFoldFunction(CodeMirror.fold.indent);
  $scope.codemirror_options = {
    onLoad: $scope.newBlueprintCodemirrorLoaded,
    theme: 'lesser-dark',
    mode: 'text/x-yaml',
    lineNumbers: true,
    autoFocus: true,
    lineWrapping: true,
    matchBrackets: true,
    onGutterClick: $scope.foldFunc,
    lint: false,
    gutters: ['CodeMirror-lint-markers']
  };

  $scope.$watch('deployment_string', $scope.refresh_parse_deployment);
}

function MagentoStackController($scope, $location) {
  $scope.currentCurrency = '$';
  $scope.go = function(path) {
    $location.path(path);
  };
  $scope.tiers = [
    {
      'title': 'Extra Small',
      'link': '/blueprints/design/cbfx/magentostack/extra-small',
      'price': 1000,
      'unit': 'month',
      'features': [
        {'title': 'Concurrent Users', 'count': 100, 'enabled': true},
        {'title': 'Cloud Database', 'count': 1, 'enabled': true},
        {'title': 'ObjectRocket Redis', 'count': 3, 'enabled': true},
        {'title': '7.5G App Server', 'count': 1, 'enabled': true}
      ]
    },
    {
      'title': 'Small',
      'link': '/blueprints/design/cbfx/magentostack/small',
      'price': 2000,
      'unit': 'month',
      'features': [
        {'title': 'Concurrent Users', 'count': 200, 'enabled': true},
        {'title': 'Cloud Database', 'count': 1, 'enabled': true},
        {'title': 'ObjectRocket Redis', 'count': 3, 'enabled': true},
        {'title': '15G App Server', 'count': 1, 'enabled': true}
      ]
    },
    {
      'title': 'Medium',
      'link': '/blueprints/design/cbfx/magentostack/medium',
      'price': 3000,
      'unit': 'month',
      'features': [
        {'title': 'Concurrent Users', 'count': 400, 'enabled': true},
        {'title': 'Cloud Database', 'count': 1, 'enabled': true},
        {'title': 'ObjectRocket Redis', 'count': 3, 'enabled': true},
        {'title': '15G App Server', 'count': 2, 'enabled': true}
      ]
    },
    {
      'title': 'Large',
      'link': '/blueprints/design/cbfx/magentostack/large',
      'price': 4000,
      'unit': 'month',
      'features': [
        {'title': 'Concurrent Users', 'count': 750, 'enabled': true},
        {'title': 'Cloud Database', 'count': 1, 'enabled': true},
        {'title': 'ObjectRocket Redis', 'count': 3, 'enabled': true},
        {'title': '30G App Server', 'count': 2, 'enabled': true}
      ]
    },
    {
      'title': 'Extra Large',
      'link': '/blueprints/design/cbfx/magentostack/extra-large',
      'price': 5000,
      'unit': 'month',
      'features': [
        {'title': 'Concurrent Users', 'count': 1125, 'enabled': true},
        {'title': 'Cloud Database', 'count': 1, 'enabled': true},
        {'title': 'ObjectRocket Redis', 'count': 3, 'enabled': true},
        {'title': '30G App Server', 'count': 3, 'enabled': true}
      ]
    }
  ];
}

checkmate.controller('DeploymentController', DeploymentController);
checkmate.controller('DeploymentListController', DeploymentListController);
checkmate.controller('BlueprintRemoteListController', BlueprintRemoteListController);
checkmate.controller('BlueprintNewController', BlueprintNewController);
checkmate.controller('DeploymentNewController', DeploymentNewController);
checkmate.controller('DeploymentNewRemoteController', DeploymentNewRemoteController);
checkmate.controller('StaticController', StaticController);
checkmate.controller('RawController', RawController);
checkmate.controller('MagentoStackController', MagentoStackController);
checkmate.controller('NavBarController', NavBarController);
checkmate.controller('AppController', AppController);
checkmate.controller('ActivityFeedController', ActivityFeedController);
checkmate.controller('TestController', TestController);
checkmate.controller('WorkflowListController', WorkflowListController);
checkmate.controller('WorkflowController', WorkflowController);
checkmate.controller('SecretsController', SecretsController);
checkmate.controller('ResourcesController', ResourcesController);


/*
 * Other stuff
 */
if (Modernizr.localstorage) {
  // window.localStorage is available!
} else {
  alert("This browser application requires an HTML5 browser with support for local storage");
}

document.addEventListener('DOMContentLoaded', function(e) {
  //On mobile devices, hide the address bar
  window.scrollTo(0, 0);
}, false);


//Instead of deprecated jQuery.browser
jQuery.uaMatch = function( ua ) {
  ua = ua.toLowerCase();
  var match = /(chrome)[ \/]([\w.]+)/.exec( ua ) ||
    /(webkit)[ \/]([\w.]+)/.exec( ua ) ||
    /(opera)(?:.*version|)[ \/]([\w.]+)/.exec( ua ) ||
    /(msie) ([\w.]+)/.exec( ua ) ||
    ua.indexOf('compatible') < 0 && /(mozilla)(?:.*? rv:([\w.]+)|)/.exec( ua ) ||
    [];
  return {
    browser: match[ 1 ] || '',
    version: match[ 2 ] || '0'
  };
};
if ( !jQuery.browser ) {
  var matched = jQuery.uaMatch( navigator.userAgent );
  var browser = {};
  if ( matched.browser ) {
    browser[ matched.browser ] = true;
    browser.version = matched.version;
  }
  // Chrome is Webkit, but Webkit is also Safari.
  if ( browser.chrome ) {
    browser.webkit = true;
  } else if ( browser.webkit ) {
    browser.safari = true;
  }
  jQuery.browser = browser;
}

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
