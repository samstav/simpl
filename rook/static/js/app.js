//Support for different URL for checkmate server in chrome extension
var is_chrome_extension = navigator.userAgent.toLowerCase().indexOf('chrome') > -1 && chrome && chrome.extension;
var checkmate_server_base = is_chrome_extension ? 'http://localhost\\:8080' : '';

//Load AngularJS
var checkmate = angular.module('checkmate', ['checkmate.filters', 'checkmate.services', 'checkmate.directives', 'ngResource', 'ngSanitize', 'ngCookies', 'ui', 'ngLocale', 'ui.bootstrap']);

//Load Angular Routes
checkmate.config(['$routeProvider', '$locationProvider', '$httpProvider', '$compileProvider', function($routeProvider, $locationProvider, $httpProvider, $compileProvider) {
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
  });

  // New UI - static pages
  $routeProvider.
  when('/deployments/new/wordpress', {
    templateUrl: '/partials/managed-cloud-wordpress.html',
    controller: DeploymentManagedCloudController
  }).when('/deployments/default', {  // for legacy compat for a while
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

  // Admin pages
  $routeProvider.
  when('/admin/status/celery', {
    templateUrl: '/partials/raw.html',
    controller: RawController
  }).
  when('/admin/status/libraries', {
    templateUrl: '/partials/raw.html',
    controller: RawController
  }).
  when('/admin/feedback', {
    templateUrl: '/partials/admin-feedback.html',
    controller: FeedbackListController
  }).
  when('/admin/deployments', {
    templateUrl: '/partials/deployments.html',
    controller: DeploymentListController
  });

  // Auto Login
  $routeProvider.
  when('/autologin', {
    templateUrl: '/partials/autologin.html',
    controller: AutoLoginController
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
  when('/:tenantId/workflows-new/:id', {
    templateUrl: '/partials/workflow-new.html',
    controller: WorkflowController,
    reloadOnSearch: false
  }).
  when('/:tenantId/workflows', {
    templateUrl: '/partials/workflows.html',
    controller: WorkflowListController
  }).
  when('/blueprints', {
    templateUrl: '/partials/blueprints-remote.html',
    controller: BlueprintRemoteListController
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

  // Allow ssh, irc URLs
  $compileProvider.urlSanitizationWhitelist(/^\s*(https?|mailto|ssh|irc):/);
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
  $scope.showStatus = false;

  $scope.carousel_interval = -1; // Stopped
  $scope.spot_write_url = "https://one.rackspace.com/display/Checkmate/Checkmate+Blueprints+Introduction";
  $scope.item_base_url = "/deployments/new?blueprint=https:%2F%2Fgithub.rackspace.com%2FBlueprints%2F";
  $scope.items1 = [
    {spot: "ready", show_name: true,  name: "Wordpress", description: null,                   url: "/deployments/new/wordpress", image: "wordpress.png"},
    {spot: "ready", show_name: true,  name: "Drupal",    description: "Managed Cloud Drupal", url: $scope.item_base_url + "drupal%23" + $scope.blueprint_ref, image: "druplicon.small_.png"},
    {spot: "ready", show_name: false, name: "PHP",       description: null,                   url: $scope.item_base_url + "php_app-blueprint%23" + $scope.blueprint_ref, image: "php.png"},
    {spot: "ready", show_name: true,  name: "Cassandra", description: null,                   url: $scope.item_base_url + "cassandra%23" + $scope.blueprint_ref, image: "cassandra.png"},
  ];
  $scope.items2 = [
    {spot: "ready", show_name: true,  name: "MongoDB", description: null,       url: $scope.item_base_url + "mongodb-replicaset%23" + $scope.blueprint_ref, image: "mongodb.png"},
    {spot: "ready", show_name: true,  name: "Awwbomb", description: "Aww Bomb", url: $scope.item_base_url + "awwbomb%23" + $scope.blueprint_ref, image: "awwbomb.png"},
    {spot: "ready", show_name: true,  name: "MySQL",   description: null,       url: $scope.item_base_url + "mysql-server%23" + $scope.blueprint_ref, image: "mysql.png"},
    {spot: "ready", show_name: false, name: "ZeroBin", description: null,       url: $scope.item_base_url + "zerobin%23" + $scope.blueprint_ref, image: "ZeroBin.png"},
  ];
  $scope.items3 = [
    {spot: "ready", show_name: false, name: "Etherpad", description: "Etherpad Lite", url: $scope.item_base_url + "etherpad-lite%23" + $scope.blueprint_ref, image: "etherpad_lite.png"},
    {spot: "ready", show_name: false, name: "Rails",    description: "Rails 4",       url: $scope.item_base_url + "rails4_app-blueprint%23" + $scope.blueprint_ref, image: "rails.png"},
    {spot: "write", show_name: true,  name: "DevStack", description: null,            url: null, image: "openstack.png"},
    {spot: "write", show_name: false, name: "NodeJS",   description: "node.js",       url: null, image: "nodejs.png"},
  ];
  $scope.items4 = [
    {spot: "write", show_name: false, name: "Django",   description: null,                     url: null, image: "django_small.png"},
    {spot: "write", show_name: true,  name: "Tomcat",   description: null,                     url: null, image: "tomcat_small.gif"},
    {spot: "write", show_name: true,  name: "Magento",  description: "Managed Cloud Magento",  url: null, image: "magento1-6.png"},
    {spot: "write", show_name: true,  name: "SugarCRM", description: "Managed Cloud SugarCRM", url: null, image: "sugarcrm-box-only.jpg"},
  ];
  $scope.items5 = [
    {spot: "write", show_name: true,  name: "Joomla", description: null, url: null, image: "joomla_small.png"},
    {spot: "write", show_name: true,  name: "Python", description: null, url: null, image: "python.png"},
    {spot: "write", show_name: false, name: "Apache", description: null, url: null, image: "apache.png"},
    {spot: "write", show_name: true,  name: "Hadoop", description: null, url: null, image: "hadoop.jpeg"},
  ];

  $scope.slides = [
    $scope.items1,
    $scope.items2,
    $scope.items3,
    $scope.items4,
    $scope.items5,
  ];

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

function AutoLoginController($scope, $location, $cookies, auth) {
  $scope.auto_login_success = function() {
    $location.path('/');
  };

  $scope.auto_login_fail = function(response) {
    mixpanel.track("Log In Failed", {'problem': response.status});
    $location.path('/');
    $scope.loginPrompt();
    auth.error_message = response.status + ". " + response.message;
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

    console.log("Submitting auto login credentials");
    return auth.authenticate(creds.endpoint, creds.username, creds.api_key, null, creds.token, null, creds.tenantId)
      .then($scope.auto_login_success, $scope.auto_login_fail);
  };
}

//Root controller that implements authentication
function AppController($scope, $http, $location, $resource, auth, $route, $q, webengage) {
  $scope.init_webengage = webengage.init;
  $scope.showHeader = true;
  $scope.showStatus = false;
  $scope.foldFunc = CodeMirror.newFoldFunction(CodeMirror.braceRangeFinder);

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
    var args = Array.prototype.slice.call(arguments);
    var username = args.shift();
    var callback = args.shift();
    if (auth.is_admin(true)) {
      auth.impersonate(username, true).then(function() {
        var result = callback.apply($scope, args);
        auth.exit_impersonation();
        return result;
      });
    } else {
      return callback.apply($scope, args);
    }
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

  $scope.check_permissions = function() {
    if ($scope.force_logout) {
      $scope.force_logout = false;
      $scope.bound_creds.username = '';
      $scope.logOut();
    }
  };

  $scope.check_token_validity = function(scope, next, current) {
    var token = auth.context.token;
    var now = new Date();

    if (token === undefined || token === null) return;
    var context_expiration = new Date(auth.context.token.expires || null);

    if (context_expiration <= now) {
      if (auth.is_impersonating()) {
        $scope.impersonate(auth.context.username)
          .then($scope.on_impersonate_success, $scope.on_auth_failed);
      } else {
        $('#modalAuth').one('hide', function(e) {
          $scope.$apply($scope.check_permissions); // TODO: is there a better way of doing this?
        });
        $scope.force_logout = true;
        $scope.bound_creds.username = auth.context.username;
        auth.error_message = "It seems your token has expired. Please log back in again.";
        $scope.loginPrompt().then($route.reload);
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

    var info = {data: error.data,
                status: error.status,
                title: "Error",
                message: "There was an error executing your request:"};
    if (typeof error.data == "object" && 'description' in error.data)
        info.message = error.data.description;
    $scope.$root.error = info;
    $scope.open_modal('error');
    mixpanel.track("Error", {'error': info.message});
  };

  $scope.$on('logIn', function() {
    $scope.message = auth.message;
    $scope.notify("Welcome, " + $scope.auth.identity.username + "! You are logged in");
  });

  $scope.$on('logOut', function() {
    $location.url('/');
  });

  $scope.auth = auth;

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
  $scope.modal_window = {};
  $scope.open_modal = function(window_name) {
    console.log("opening modal...");
    $scope.modal_window[window_name] = true;
  };
  $scope.close_modal = function(window_name) {
    $scope.modal_window[window_name] = false;
  };

  $scope.hidden_alerts = {};
  $scope.hide_alert = function(alert_id) {
    $scope.hidden_alerts[alert_id] = true;
  };
  $scope.display_alert = function(alert_id) {
    return !$scope.hidden_alerts[alert_id];
  };

  // Display log in prompt
  $scope.deferred_login = null;
  $scope.display_login_prompt = false;
  $scope.login_prompt_opts = {
    backdropFade: true,
    dialogFade: true,
  };
  $scope.loginPrompt = function() {
    $scope.deferred_login = $q.defer();
    $scope.display_login_prompt = true;
    // TODO: focus on username field
    return $scope.deferred_login.promise;
  };
  $scope.close_login_prompt = function() {
    $scope.clear_login_form();
    $scope.display_login_prompt = false;
    if ($scope.deferred_login !== null) {
      $scope.deferred_login.reject({ logged_in: false, reason: 'dismissed' });
    }
  };

  $scope.clear_login_form = function() {
    $scope.bound_creds.username = null;
    $scope.bound_creds.password = null;
    $scope.bound_creds.apikey   = null;
    auth.error_message = null;
  }

  $scope.on_auth_success = function() {
    $scope.close_login_prompt();
    $scope.deferred_login.resolve({ logged_in: true });
    $scope.deferred_login = null;

    mixpanel.track("Logged In", {'user': $scope.auth.identity.username});
  };

  $scope.auth_error_message = function() { return auth.error_message; };
  $scope.on_auth_failed = function(response) {
    mixpanel.track("Log In Failed", {'problem': response.status});
    auth.error_message = response.status + ". Check that you typed in the correct credentials.";
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
    return JSON.parse(local_endpoint) || auth.selected_endpoint || auth.endpoints[0] || {};
  };

  // Log in using credentials delivered through bound_credentials
  $scope.logIn = function() {
    $scope.force_logout = false; // TODO: is there a better way of doing this?
    var username = $scope.bound_creds.username;
    var password = $scope.bound_creds.password;
    var apikey = $scope.bound_creds.apikey;
    var pin_rsa = $scope.bound_creds.pin_rsa;
    auth.error_message = null;

    //Handle auto_complete sync issues (1Pass, LastPass do not update scope)
    try {
      var login_form = window.document.forms.loginForm;

      var realvalue = loginForm.username.value;
      if (realvalue !== undefined && username != realvalue)
        username = realvalue;

      realvalue = loginForm.password.value;
      if (realvalue !== undefined && password != realvalue)
        password = realvalue;

      realvalue = loginForm.apikey.value;
      if (realvalue !== undefined && apikey != realvalue)
        apikey = realvalue;

      //!Pass puts the password in the apikey field too. Assume it's password
      if (password == apikey)
        apikey = undefined;
    } catch(err) {
      console.log(err);
    }

    var endpoint = $scope.get_selected_endpoint();
    return auth.authenticate(endpoint, username, apikey, password, null, pin_rsa, null)
      .then($scope.on_auth_success, $scope.on_auth_failed);
  };

  $scope.logOut = function() {
    auth.error_message = null;
    auth.logOut();
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
    mixpanel.track("Impersonation Failed");
    $scope.$root.error = {
      data: response.data,
      status: response.status,
      title: "Error Impersonating User",
      message: "There was an error during impersonation:"
    };
    $scope.open_modal('error');
  }

  $scope.impersonation = { username: "" };
  $scope.impersonate = function(username) {
    mixpanel.track("Impersonation", { user: auth.identity.username, tenant: username });
    $scope.impersonation.username = "";
    return auth.impersonate(username)
      .then($scope.on_impersonate_success, $scope.on_impersonate_error);
  };

  $scope.exit_impersonation = function() {
    auth.exit_impersonation();
    $location.url('/');
  };

  $scope.is_impersonating = function() {
    return auth.is_impersonating();
  };

  $scope.in_admin_context = function() {
    return auth.identity.is_admin && !auth.is_impersonating();
  };

  // Utility Functions
  console.log("Getting api version");
  var api = $resource((checkmate_server_base || '') + '/version');
  api.get(function(data, getResponseHeaders){
    $scope.api_version = data.version;
    console.log("Got api version: " + $scope.api_version);
    //Check if simulator enabled
    $scope.$root.simulator = getResponseHeaders("X-Simulator-Enabled");
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

  console.log("Getting rook version");
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
        mixpanel.track("Feedback Sent");
    }).error(function(response) {
      $("#feedback_error_text").html(response.statusText);
      $("#feedback_error").show();
      mixpanel.track("Feedback Failed");
    });
  };
}

function ActivityFeedController($scope, $http, items) {
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
    default:
    }
    return parsed;
  };

  $scope.load = function() {
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
        var response = {data: data, status: status};
        $scope.loading = false;
      });
  };
  $scope.load();
}

function TestController($scope, $location, $routeParams, $resource, $http, items, navbar, options, workflow) {
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

      $scope.deployment = deployments.get(params, function () { $scope.start_tree_preview('#workflow_tree') });

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
          if ($scope.auto_refresh !== false)
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
            console.log("Error " + error.data + "(" + error.status + ") loading deployment.");
            $scope.$root.error = {data: error.data, status: error.status, title: "Error loading deployment",
                    message: "There was an error loading your deployment:"};
            $scope.open_modal('error');
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
        $scope.$root.error = info;
      if ($location.path().indexOf('deployments') == -1)
        $scope.open_modal('error');  //don't show error when in deployment screen
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
          mixpanel.track("Task Spec Saved");
        }, function(error) {
          $scope.$root.error = {data: error.data, status: error.status, title: "Error Saving",
                  message: "There was an error saving your JSON:"};
          $scope.open_modal('error');
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
          mixpanel.track("Task Saved");
        }, function(error) {
          $scope.$root.error = {data: error.data, status: error.status, title: "Error Saving",
                  message: "There was an error saving your JSON:"};
          $scope.open_modal('error');
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
    mixpanel.track("Workflow Action", {'action': action});
    $scope.load();
  }

  $scope.workflow_action_error = function(response) {
    var action = response.config.url.replace($location.path() + '/+', '');
    mixpanel.track("Workflow Action Failed", {'action': action});
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
          mixpanel.track("Task Action", {'action': action});
        }).error(function(data) {
          $scope.show_error(data);
          mixpanel.track("Task Action Failed", {'action': action});
        });
    } else {
      $scope.loginPrompt().then(retry);
    }
  };

  $scope.execute_task = function() {
    return $scope.task_action($scope.current_task.id, 'execute');
  };

  $scope.reset_task = function() {
    $scope.close_modal('reset_warning');
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

  $scope.cancel_auto_refresh = function() {
    if ($scope.auto_refresh_promise)
      $timeout.cancel($scope.auto_refresh_promise);
  }

  $scope.$on('$routeChangeStart', $scope.cancel_auto_refresh);

  $scope.start_task_name = 'Start';
  $scope.padding = 8;
  $scope.group_spacing = 10;
  $scope.collision_spacing = 7;
  $scope.default_task_duration = $scope.group_spacing;
  $scope.log_scale = 15;
  $scope.canvas = {
    width: 1080,
    height: 300
  };

  $scope.getIcon = function(node) {
    var icon = '';
    var color = '';
    var base_dir = "/img/icons/";
    var resource_id = node.spec.properties.resource || '';
    var resource = '';

    if ($scope.deployment.resources && $scope.deployment.resources[resource_id]) {
      resource = $scope.deployment.resources[resource_id].type;
      color = $scope.color(node);
    }

    icon = resource;
    if (['database', 'load-balancer', 'compute'].indexOf(icon) === -1) icon = '';
    if (icon != '') icon = base_dir + icon + '-' + color + '.svg';

    return icon;
  }

  $scope.distanceToStartSpec = function(memo, all_specs, spec) {
    if(memo[spec.id]) {
      return memo[spec.id];
    }

    if(spec.id === 1){
      memo[spec.id] = 0;
      return memo[spec.id];
    }

    max_spec = _.max(spec.inputs, function(input){
      return $scope.distanceToStartSpec(memo, all_specs, specs[input]);
    });

    var max_duration = specs[max_spec].properties.estimated_duration || $scope.default_task_duration;
    memo[spec.id] = memo[specs[max_spec].id] + Math.log(max_duration) * $scope.log_scale;
    return memo[spec.id];
  }

  $scope.resource_position = function(group) {
    return group * $scope.group_spacing;
  }

  $scope.avoid_collision = function(nodes, current_position, axis, level) {
    level = level || 0;
    var new_position = angular.copy(current_position);
    var existing_node = _.findWhere(nodes, new_position);
    if (!existing_node) {
      return new_position;
    }
    new_position[axis] += $scope.collision_spacing;
    return $scope.avoid_collision(nodes, new_position, axis, level+1);
  }

  $scope.getGroup = function(spec, specs) {
    var group;
    var no_group = -1;
    var shift_size = 2;

    if (spec.properties.resource)
      group = parseInt(spec.properties.resource) || no_group;
    else
      group = parseInt(specs[spec.inputs[0]].properties.resource) || no_group;

    group += shift_size;
    return group;
  }

  $scope.get_limits = function(nodes) {
    var limits = {
      min: { x:  Infinity, y:  Infinity },
      max: { x: -Infinity, y: -Infinity }
    };

    _.each(nodes, function(node) {
      if (node.x < limits.min.x) limits.min.x = node.x;
      if (node.y < limits.min.y) limits.min.y = node.y;

      if (node.x > limits.max.x) limits.max.x = node.x;
      if (node.y > limits.max.y) limits.max.y = node.y;
    });

    limits.size = {
      x: limits.max.x - limits.min.x,
      y: limits.max.y - limits.min.y
    }

    return limits;
  }

  $scope.interpolate_nodes = function(nodes) {
    var interpolated_nodes = angular.copy(nodes);
    var limits = $scope.get_limits(interpolated_nodes);

    _.each(interpolated_nodes, function(node) {
      var new_x = ($scope.canvas.width - ($scope.padding * 2))  * (node.x - limits.min.x) / limits.size.x;
      var new_y = ($scope.canvas.height - ($scope.padding * 2)) * (node.y - limits.min.y) / limits.size.y;
      node.x = new_x + $scope.padding;
      node.y = new_y + $scope.padding;
      if (node.name == $scope.start_task_name)
        node.y = $scope.canvas.height / 2;
    });

    return interpolated_nodes;
  }

  $scope.buildNodes = function(specs) {
    var nodes = [];
    var start_group = 0;
    var positions_memo = {};
    var start_position = { x: 0, y: 0 };
    var fixed_status = true;
    var skip_nodes = ['Root', 'Start'];
    var start_spec = 'Start';

    _.each(specs, function(spec, spec_name){
      var node = {};
      if(spec_name === start_spec) {
        node.fixed = fixed_status;
        node.name = spec_name;
        node.group = start_group;
        node.x = start_position.x;
        node.y = start_position.y;
        node.spec = spec;

        nodes.push(node);
      }

      if(spec.properties) {
        if ( skip_nodes.indexOf(spec_name) === -1 ) {
          var group = $scope.getGroup(spec, specs);
          var distance = $scope.distanceToStartSpec(positions_memo, specs, spec);
          var row = $scope.resource_position(group);
          var current_position = { x: distance, y: row };
          var position = $scope.avoid_collision(nodes, current_position, 'y');
          node.fixed = fixed_status;
          node.name = spec_name;
          node.group = group;
          node.x = position.x;
          node.y = position.y;
          node.spec = spec;
          if(_.contains(spec.properties.task_tags, 'root'))
            node.resource_number = spec.defines.resource;

          nodes.push(node)
        }
      }
    });

    return $scope.interpolate_nodes(nodes);
  }

  $scope.buildLinks = function(specs, nodes) {
    var links = [];

    _.each(specs, function(spec, spec_name) {
      if(spec.outputs) {
        _.each(spec.outputs, function(output) {
          source = _.findWhere(nodes, { name: spec_name });
          target = _.findWhere(nodes, { name: output });
          if(source && target) {
            var link = {source: source, target: target, value: 1}
            links.push(link);
          }
        });
      }
    });

    return links;
  }

  $scope.color = function(node) {
    var color;
    var state = $scope.spec_status(node.name);
    switch($scope.state_name({state: state})) {
      case "Ready":
      case "Completed":
        color = 'green';
        break;
      case "Waiting":
        color = 'orange';
        break;
      case "Error":
        color = 'red';
        break;
      case "Future":
      case "Likely":
      case "Maybe":
        color = 'gray';
        break;
      default:
        color = 'black';
        break;
    }
    return color;
  }

  $scope.update_nodes = function(nodes, svg) {
    var data = svg.select('#nodes').selectAll('g.node').data(nodes);

    // Enter
    var enter_nodes = data.enter()
      .append('svg:g')
      .attr('class', 'node')
      .attr('cursor', 'pointer')
      .on('click', function(d){
        d3.select("#highlight").remove();

        svg.insert('g', ':first-child')
          .attr("transform", function() { return "translate(" + d.x + "," + d.y + ")"; })
          .insert('circle', ':first-child')
          .attr('id', 'highlight')
          .attr('r', 36)
          .attr('x', d.x)
          .attr('y', d.y)
          .style('fill', 'url(#gradient)');

        $scope.$apply(function() {
          $scope.selectSpec(d.name);
        });
      });
    enter_nodes.append('svg:title').text(function(d) { return d.name; });
    enter_nodes.append('svg:desc') .text(function(d) { return JSON.stringify(d); });

    enter_nodes.append("text")
      .attr("class", "nodetext")
      .attr("dx", -40)
      .attr("dy", -10)
      .text(function(d) {
        var display_name = '';
        if(d.resource_number){
          if($scope.deployment && $scope.deployment.resources) {
            display_name = $scope.deployment.resources[d.resource_number]['dns-name']
          }
        }
        return display_name;
      });

    enter_nodes.append('circle')
      .attr('class', 'node')
      .attr('r', 6);
    enter_nodes.append('svg:image')
      .attr('xlink:href', $scope.getIcon)
      .attr('x', '-16px')
      .attr('y', '-16px')
      .attr('width', '32px')
      .attr('height', '32px');
    enter_nodes.attr("transform", function(d) { return "translate(" + d.x + "," + d.y + ")"; });

    // Update
    data.select('circle').style('fill', function(d) { return $scope.color(d); });
    data.select('image').attr('xlink:href', $scope.getIcon);

    // Exit
    data.exit().remove();

    return data;
  }

  $scope.update_links = function(links, svg) {
    var data = svg.select('#links').selectAll('line.link').data(links);

    // Enter
    var enter_links = data.enter()
      .append('line')
      .attr('class', 'link')
      .attr('x1', function(d) { return d.source.x; })
      .attr('y1', function(d) { return d.source.y; })
      .attr('x2', function(d) { return d.target.x; })
      .attr('y2', function(d) { return d.target.y; })
      ;

    // Exit
    data.exit().remove();

    return data;
  }

  $scope.buildNetwork = function(json, parent_element) {
    var svg = d3.select(parent_element);

    var gradient = svg.append("svg:defs")
    .append("svg:radialGradient")
    .attr("id", "gradient")

    gradient.append("svg:stop")
    .attr("offset", "0%")
    .attr("stop-color", "#0E90D2")
    .attr("stop-opacity", 1);

    gradient.append("svg:stop")
    .attr("offset", "100%")
    .attr("stop-color", "#F5F5F5")
    .attr("stop-opacity", 1);

    if (svg.select('g#links')[0][0] === null)
      svg.append('g').attr('id', 'links');
    $scope.update_links(json.links, svg);

    if (svg.select('g#nodes')[0][0] === null)
      svg.append('g').attr('id', 'nodes');
    $scope.update_nodes(json.nodes, svg);
  };

  $scope.start_tree_preview = function(parent_element) {
    if($scope.data){
      specs = $scope.data.wf_spec.task_specs
      var nodes = $scope.buildNodes(specs);
      var links = $scope.buildLinks(specs, nodes);
      var network = { nodes: nodes, links: links };
      $scope.buildNetwork(network, parent_element);
    }
  };
}

//Blueprint controllers
function BlueprintListController($scope, $location, $routeParams, $resource, items, navbar, options, workflow, blueprints, initial_blueprint, environments, initial_environment) {
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
    mixpanel.track("Blueprint Selected", {'blueprint': $scope.selected.key});
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
  DeploymentNewController($scope, $location, $routeParams, $resource, options, workflow, $scope.selected, $scope.environment);

  //Wire Blueprints to Deployment
  $scope.$watch('selected', function(newVal, oldVal, scope) {
    if (typeof newVal == 'object') {
       $scope.setBlueprint(blueprints[newVal.key]);
    }
  });
}

function BlueprintRemoteListController($scope, $location, $routeParams, $resource, $http, items, navbar, options, workflow, github) {
  //Inherit from Blueprint List Controller
  BlueprintListController($scope, $location, $routeParams, $resource, items, navbar, options, workflow, {}, null, {}, null);
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
    return ['https://github.rackspace.com/Blueprints'];
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
      return github.get_contents($scope.remote, blueprint.api_url, "checkmate.yaml", function(content_data){
        if(content_data.type === 'file'){
          blueprint.is_blueprint_repo = true;

          updateBlueprintCache([blueprint]);

          blueprint.is_fresh = true;

          updateListWithBlueprint($scope.items, blueprint)
        }
      });
    }

    var received_items = items.receive(data, function(item, key) {
      if (!('documentation' in item))
        item.documentation = {abstract: item.description};
      return { key: item.id,
               id: item.html_url,
               name: item.name,
               description: item.documentation.abstract,
               git_url: item.git_url,
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
               function(memo, item) { return memo.then(function(){ return verifyBlueprintRepo(item) }, function(){ return verifyBlueprintRepo(item) }) },
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
    return keys.length != 0;
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
    for (var id in $scope.selected_deployments) {
      var deployment = $scope.deployment_map[id];
      if (deployment) {
        $scope.wrap_admin_call(deployment.created_by, $scope.sync, deployment);
      }
    }
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

  // This also exists on DeploymentController - can be refactored
  $scope.sync = function(deployment) {
    var retry = function() {
      $scope.sync(deployment);
    };

    if (auth.is_logged_in()) {
      var klass = $resource((checkmate_server_base || '') + '/:tenantId/deployments/:deployment_id/+sync.json', null, {'get': {method:'GET'}});
      var thang = new klass();
      thang.$get({tenantId: deployment.tenantId, deployment_id: deployment['id']}, function(returned, getHeaders){
          // Sync
          if (returned !== undefined)
              $scope.notify(Object.keys(returned).length + ' resources synced');
        }, function(error) {
          $scope.$root.error = {data: error.data, status: error.status, title: "Error Deleting",
                  message: "There was an error syncing your deployment"};
          $scope.open_modal('error');
        });
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
function DeploymentManagedCloudController($scope, $location, $routeParams, $resource, $http, items, navbar, options, workflow, github) {

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
    mixpanel.track("Remote Blueprint Requested", {'blueprint': repo_url});
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
                          WPBP, null, ENVIRONMENTS, 'next-gen');

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
    $scope.loadRemoteBlueprint('https://github.rackspace.com/Blueprints/wordpress#stable');
    $scope.loadRemoteBlueprint('https://github.rackspace.com/Blueprints/wordpress-clouddb#stable');

    //Load the latest master from github
    $scope.loadRemoteBlueprint('https://github.rackspace.com/Blueprints/wordpress#master');
    $scope.loadRemoteBlueprint('https://github.rackspace.com/Blueprints/wordpress-clouddb#master');
  }

  $('#mcspec_list').css('top', $('.summaryHeader').outerHeight()); // Not sure if this is the right place for this. -Chris.Burrell (chri5089)
}

//Select one remote blueprint
function DeploymentNewRemoteController($scope, $location, $routeParams, $resource, $http, items, navbar, options, workflow, github) {

  var blueprint = $location.search().blueprint;
  if (blueprint === undefined)
    blueprint = "https://github.rackspace.com/Blueprints/helloworld";
  var u = URI(blueprint);
  if (u.fragment() === "") {
    u.fragment($location.hash() || 'master');
    $location.hash("");
    $location.search('blueprint', u.normalize());
  }

  BlueprintRemoteListController($scope, $location, $routeParams, $resource, $http, items, navbar, options, workflow, github);

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
function DeploymentNewController($scope, $location, $routeParams, $resource, options, workflow, blueprint, environment) {
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
      var url = '/:tenantId/providers/rackspace.dns/proxy/v1.0/:tenantId/domains.json';
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

  $scope.submit = function(action) {
    if ($scope.submitting === true)
      return;
    $scope.submitting = true;
    var url = '/:tenantId/deployments';
    if ((action !== undefined) && action)
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

    break_flag = false;

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
          $scope.notify(err_msg);
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

    if (break_flag){
      $scope.submitting = false;
      return;
    }

    if ($scope.auth.identity.loggedIn) {
        mixpanel.track("Deployment Launched", {'action': action});
        deployment.$save(function(returned, getHeaders){
        if (action == '+preview') {
            workflow.preview = returned;
            $location.path('/' + $scope.auth.context.tenantId + '/workflows/+preview');
        } else {
            var deploymentId = getHeaders('location').split('/')[3];
            console.log("Posted deployment", deploymentId);
            $location.path(getHeaders('location'));
            /*  -- old workflow logic
            //Hack to get link
            try {
              var workflowId = getHeaders('link').split(';')[0]; //Get first part
              workflowId = workflowId.split('/'); //split URL
              workflowId = workflowId[workflowId.length - 1].trim(); //get ID
              workflowId = workflowId.substr(0, workflowId.length - 1);  //trim
              $location.path('/' + $scope.auth.context.tenantId + '/workflows/' + workflowId + '/status');
            } catch(err) {
              //Fail-safe to old logic of deploymentId=workflowId
              console.log("Error processing link header", err);
              $location.path('/' + $scope.auth.context.tenantId + '/workflows/' + deploymentId + '/status');
            }
            */
        }
      }, function(error) {
        console.log("Error " + error.data + "(" + error.status + ") creating new deployment.");
        console.log(deployment);
        $scope.$root.error = {data: error.data, status: error.status, title: "Error Creating Deployment",
                message: "There was an error creating your deployment:"};
        $scope.open_modal('error');
        $scope.submitting = false;
        mixpanel.track("Deployment Launch Failed", {'status': error.status, 'data': error.data});
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
function SecretsController($scope, $location, $resource, $routeParams, dialog) {
  $scope.dialog = dialog;

  $scope.load = function() {
    console.log("Starting load");
    this.klass = $resource((checkmate_server_base || '') + $location.path() + '/secrets.json');
    $scope.secrets = this.klass.get($routeParams, function(data, getResponseHeaders){
      $scope.data = data;
    });
  };

  $scope.dismissSecrets = function() {
    _.each($scope.secrets.secrets, function(element) {
      element.status = 'LOCKED';
    });
    $scope.secrets.$save();
  };

  $scope.allAvailableSecrets = function() {
    var result = '';
    _.each($scope.secrets.secrets, function(element, key) {
      if (element.status == 'AVAILABLE')
        result = result + key + ': ' + element.value + '\n';
    });
    return result;
  };

  $scope.load();
}

//Handles an existing deployment
function DeploymentController($scope, $location, $resource, $routeParams, $dialog, deploymentDataParser, $http, urlBuilder, Deployment, workflow) {
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

  $scope.showSecrets = function() {
    $scope.secretsDialog = $dialog.dialog({
        resolve: {
            dialog: function() {return $scope.secretsDialog;}
        }
    }).open('/partials/secrets.html', 'SecretsController');
  };

  $scope.shouldDisplayWorkflowStatus = function() {
    var operation = $scope.data.operation;
    if(operation){
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
    if(!operation || (operation.link && !(operation.link.indexOf('canvases') === -1)))
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

  $scope.load = function() {
    console.log("Starting load");
    this.klass = $resource((checkmate_server_base || '') + $location.path() + '.json');
    this.klass.get($routeParams, function(data, getResponseHeaders){
      $scope.data_json = JSON.stringify(data, null, 2);

      $scope.load_workflow_stats(data.operation);
      data.display_status = Deployment.status(data);
      $scope.data = data;
      $scope.resources = _.values($scope.data.resources);
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

  $scope.add_nodes = function(deployment, service, num_nodes) {
    Deployment.add_nodes(deployment, service, num_nodes)
      .then($scope.load, $scope.show_error);
  };

  $scope.delete_nodes = function(deployment, resources) {
    Deployment.delete_nodes(deployment, resources)
      .then($scope.load, $scope.show_error);
  };

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
    mixpanel.track('Deployment::Retry', { deployment_id: $scope.data.id });
  }

  $scope.resume = function() {
    var url = $scope.data.operation['resume-link'];
    $http.post(url);
    mixpanel.track('Deployment::Resume', { deployment_id: $scope.data.id });
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
          $scope.$root.error = {data: error.data, status: error.status, title: "Error Saving",
                  message: "There was an error saving your JSON:"};
          $scope.open_modal('error');
        });
    } else {
      $scope.loginPrompt().then($scope.save);
    }
  };

  $scope.delete_deployment = function(force) {
    var retry = function() {
      $scope.delete_deployment(force);
    };

    if (force == '1') {
      $scope.close_modal('force_delete_warning');
    } else {
      $scope.close_modal('delete_warning');
    }
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
          $scope.$root.error = {data: error.data, status: error.status, title: "Error Deleting",
                  message: "There was an error deleting your deployment"};
          $scope.open_modal('error');
        });
    } else {
      $scope.loginPrompt().then(retry);
    }
  };

  // This also exists on DeploymentListController - can be refactored
  $scope.sync = function() {
    if ($scope.auth.is_logged_in()) {
      var klass = $resource((checkmate_server_base || '') + '/:tenantId/deployments/:deployment_id/+sync.json', null, {'get': {method:'GET'}});
      var thang = new klass();
      thang.$get({tenantId: $scope.data.tenantId, deployment_id: $scope.data['id']}, function(returned, getHeaders){
          // Sync
          $scope.load();
          if (returned !== undefined)
              $scope.notify(Object.keys(returned).length + ' resources synced');
        }, function(error) {
          $scope.$root.error = {data: error.data, status: error.status, title: "Error Deleting",
                  message: "There was an error syncing your deployment"};
          $scope.open_modal('error');
        });
    } else {
      $scope.loginPrompt().then($scope.sync);
    }
  };

  $scope.tree_data = null;
  $scope.vertex_groups = {
    // Standard architecture
    lb: 0,
    master: 1,
    web: 1,
    app: 1,
    admin: 1,
    backend: 2,

    // Cassandra
    seed: 0,
    node: 1,

    // Mongo
    primary: 0,
    data: 1
  };

  $scope.create_vertex = function(resource, resource_list) {
    var v1 = resource.index;
    var group = resource.service;
    var dns_name = resource['dns-name'] || '';
    var name = dns_name.split('.').shift();
    var host_id = resource.hosted_on;
    var host = resource_list[host_id];

    var vertex = {
      id: resource.index,
      group: group,
      component: resource.component,
      name: name,
      status: resource.status,
      host: {}
    };
    if (host) {
      vertex.host = {
        id: host.index,
        status: host.status,
        type: host.component
      };
    }
    return vertex;
  };

  $scope.create_edges = function(vertex, relations) {
    var edges = [];

    var v1 = vertex.id;
    for (var i in relations) {
      var relation = relations[i];
      if (relation.relation != 'reference') continue;

      var v2 = relation.source || relation.target;
      var sorted_edges = [v1, v2].sort();
      var edge = { v1: sorted_edges[0], v2: sorted_edges[1] };
      edges.push(edge);
    }

    return edges;
  }

  $scope.build_tree = function() {
    var edges = [];
    var vertices = [];
    var resources = $scope.data.resources;

    for (var i in resources) {
      var resource = resources[i];
      if (!resource.relations) continue;

      // Vertices
      var vertex = $scope.create_vertex(resource, resources);
      var group_idx = $scope.vertex_groups[vertex.group] || 0;
      if (!vertices[group_idx]) vertices[group_idx] = [];
      vertices[group_idx].push(vertex);

      // Edges
      edges = edges.concat($scope.create_edges(vertex, resource.relations));
    }

    $scope.tree_data = { vertex_groups: vertices, edges: edges };
    return $scope.tree_data;
  }
  $scope.$watch('data', $scope.build_tree);
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


/*
 * Other stuff
 */
if (Modernizr.localstorage) {
  // window.localStorage is available!
} else {
  alert("This browser application requires an HTML5 browser with support for local storage");
}

var foldFunc = CodeMirror.newFoldFunction(CodeMirror.braceRangeFinder);

document.addEventListener('DOMContentLoaded', function(e) {
  //On mobile devices, hide the address bar
  window.scrollTo(0, 0);
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
