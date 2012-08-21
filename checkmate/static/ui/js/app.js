var checkmate = angular.module('checkmate', ['checkmate.filters', 'checkmate.services', 'checkmate.directives', 'ngResource', 'ngSanitize', 'ngCookies', 'ui']);

checkmate.config(['$routeProvider', '$locationProvider', '$httpProvider', function($routeProvider, $locationProvider, $httpProvider) {
  // Static Paths
  $routeProvider.
  when('/', {
    templateUrl: '/static/ui/partials/home.html',
    controller: StaticController
  }).
  when('/readme', {
    templateUrl: '/static/ui/partials/readme.html',
    controller: StaticController
  }).
  when('/ui/build', {
    templateUrl: '/static/ui/partials/calculator.html',
    controller: StaticController
  })

  // Legacy Paths
  $routeProvider.
  when('/:tenantId/environments', {
    controller: LegacyController,
    template:'<section class="entries" ng-include="templateUrl"><img src="/static/img/ajax-loader-bar.gif" alt="Loading..."/></section>'
  }).
  when('/:tenantId/environments/:id', {
    controller: LegacyController,
    template:'<section class="entries" ng-include="templateUrl"><img src="/static/img/ajax-loader-bar.gif" alt="Loading..."/></section>'
  }).
  when('/:tenantId/deployments', {
    controller: LegacyController,
    template:'<section class="entries" ng-include="templateUrl"><img src="/static/img/ajax-loader-bar.gif" alt="Loading..."/></section>'
  }).
  when('/:tenantId/deployments/:id', {
    controller: LegacyController,
    template:'<section class="entries" ng-include="templateUrl"><img src="/static/img/ajax-loader-bar.gif" alt="Loading..."/></section>'
  }).
  when('/:tenantId/blueprints', {
    controller: LegacyController,
    template:'<section class="entries" ng-include="templateUrl"><img src="/static/img/ajax-loader-bar.gif" alt="Loading..."/></section>'
  }).
  when('/:tenantId/workflows', {
    controller: LegacyController,
    template:'<section class="entries" ng-include="templateUrl"><img src="/static/img/ajax-loader-bar.gif" alt="Loading..."/></section>'
  }).
  when('/:tenantId/workflows/:id', {
    controller: LegacyController,
    template:'<section class="entries" ng-include="templateUrl"><img src="/static/img/ajax-loader-bar.gif" alt="Loading..."/></section>'
  }).
  when('/:tenantId/workflows/:id/tasks/:task_id', {
    controller: LegacyController,
    template:'<section class="entries" ng-include="templateUrl"><img src="/static/img/ajax-loader-bar.gif" alt="Loading..."/></section>'
  }).
  when('/providers', {
    controller: LegacyController,
    template:'<section class="entries" ng-include="templateUrl"><img src="/static/img/ajax-loader-bar.gif" alt="Loading..."/></section>'
  }).
  when('/status/libraries', {
    controller: LegacyController,
    template:'<section class="entries" ng-include="templateUrl"><img src="/static/img/ajax-loader-bar.gif" alt="Loading..."/></section>'
  }).
  when('/status/celery', {
    controller: LegacyController,
    template:'<section class="entries" ng-include="templateUrl"><img src="/static/img/ajax-loader-bar.gif" alt="Loading..."/></section>'
  })
  
  // New UI - static pages
  $routeProvider.
  when('/deployments/default', {
    templateUrl: '/static/ui/partials/deployment-new.html',
    controller: DeploymentTryController
  }).
  when('/deployments/new', {
    templateUrl: '/static/angular/partials/deployment-new.html',
    controller: DeploymentNewController
  })

  // New UI - dynamic, tenant pages
  $routeProvider.
  when('/new/:tenantId/workflows/:id', {
    templateUrl: '/static/ui/partials/level2.html',
    controller: WorkflowController
  }).
  when('/:tenantId/blueprints/:id', {
    templateUrl: '/static/ui/partials/level2.html',
    controller: BlueprintListController
  }).
  otherwise({});  //normal browsing
  
  
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

//Loads static content
function StaticController($scope) {
  $scope.showHeader = false;
  $scope.showStatus = false;
}

//Loads the old ui (rendered at the server)
function LegacyController($scope, $location, $routeParams, $resource, navbar, $http) {
  $scope.showHeader = false;
  $scope.showStatus = false;
  parts = $location.path().split('/')
  if (parts.length > 1)
    navbar.highlight(parts[2]);

  if ('tenantId' in $routeParams) {
    path = $location.path();
  } else if ($location.path().indexOf('/' + $scope.$parent.auth.tenantId + '/') == 0) {
    path = $location.path();
  } else {
    path = '/' + $scope.$parent.auth.tenantId + $location.path();
  }
  if (path.indexOf(".html") == -1 )
    path += ".html";
  console.log("Legacy controller loading " + path);
  $scope.templateUrl = path;

  $scope.save = function() {
    var klass = $resource($location.path());
    var thang = new klass(JSON.parse(Editor.getValue()));

    if ($scope.auth.loggedIn) {
        thang.$save(function(returned, getHeaders){
          alert('Saved');
          console.log(returned);
      }, function(error) {
        console.log("Error " + error.data + "(" + error.status + ") saving this object.");
        console.log($("#editor").text());
        $scope.$root.error = {data: error.data, status: error.status, title: "Error Saving",
                message: "There was an error saving your JSON:"};
        $('#modalError').modal('show');
      });
    } else {
      $scope.loginPrompt(); //TODO: implement a callback
    }
  };

  $scope.action = function(action) {
    if ($scope.auth.loggedIn) {
      console.log("Executing action " + $location.path() + '/' + action)
      $http({method: 'POST', url: $location.path() + '/' + action}).
        success(function(data, status, headers, config) {
          alert('Saved');
          // this callback will be called asynchronously
          // when the response is available
        });
    } else {
      $scope.loginPrompt(); //TODO: implement a callback
    }
  };
}

// Root controller that implements authentication
function AppController($scope, $http, $location) {
  $scope.showHeader = true;
  $scope.showStatus = false;
  $scope.auth = {
      username: '',
      tenantId: '',
      expires: ''
    };

  // Restore login from session
  var catalog = localStorage.getItem('auth');
  if (catalog != undefined && catalog !== null)
    catalog = JSON.parse(catalog);
  if (catalog != undefined && catalog !== null && catalog != {} && 'access' in catalog) {
      $scope.auth.catalog = catalog;
      $scope.auth.username = catalog.access.user.name;
      $scope.auth.tenantId = catalog.access.token.tenant.id;
      checkmate.config.header_defaults.headers.common['X-Auth-Token'] = catalog.access.token.id;
      checkmate.config.header_defaults.headers.common['X-Auth-Source'] = catalog.auth_url;
      var expires = new Date(catalog.access.token.expires);
      var now = new Date();
      if (expires < now) {
        $scope.auth.expires = 'expired';
        $scope.auth.loggedIn = false;
      } else {
        $scope.auth.expires = expires - now;
        $scope.auth.loggedIn = true;
      }
  } else {
    $scope.auth.loggedIn = false;
  }

  // Bind to logon modal
  $scope.bound_creds = {
    username: '',
    password: '',
    apikey: '',
    auth_url: "https://identity.api.rackspacecloud.com/v2.0/tokens"
  };
  
  $scope.refresh = function() {
  };

  $scope.handleSpace = function() {
  };
  
  // Display log in prompt
  $scope.loginPrompt = function() {
    var modal = $('#modalAuth');
    modal.modal({
      keyboard: false,
      show: true
    });

    modal.modal('show');
  }

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

    return $.ajax({
      type: "POST",
      contentType: "application/json; charset=utf-8",
      headers: {
        "X-Auth-Source": auth_url
      },
      dataType: "json",
      url: "/authproxy",
      data: data
    }).success(function(json) {
      $('#modalAuth').modal('hide');
      var keep = {access: {token: json.access.token, user: json.access.user}};
      keep.auth_url = auth_url;  // save for later
      var expires = new Date(json.access.token.expires);
      keep.expires = expires;
      localStorage.setItem('auth', JSON.stringify(keep));
      $scope.auth.username = username;
      $scope.auth.tenantId = json.access.token.tenant.id;
      $scope.auth.catalog = json;
      checkmate.config.header_defaults.headers.common['X-Auth-Token'] = json.access.token.id;
      checkmate.config.header_defaults.headers.common['X-Auth-Source'] = auth_url;
      var now = new Date();
      if (expires < now) {
        $scope.auth.expires = 'expired';
      } else {
        $scope.auth.expires = expires - now;
      }
      $scope.auth.loggedIn = true;
      $scope.bound_creds = {
          username: '',
          password: '',
          apikey: '',
          auth_url: "https://identity.api.rackspacecloud.com/v2.0/tokens"
        };
      $scope.$apply();
    }).error(function() {
      $("#auth_error_text").html("Something bad happened");
      $("#auth_error").show();
    });
  }
  
  $scope.logOut = function() {
    $scope.auth.username = '';
    $scope.auth.catalog = null;
    localStorage.removeItem('auth');
    $scope.auth.loggedIn = false;
    delete checkmate.config.header_defaults.headers.common['X-Auth-Token'];
    delete checkmate.config.header_defaults.headers.common['X-Auth-Source'];
    $location.path('/');
  }
}

//Not really used now
function NavBarController() {

}

/**
 *   workflows
 */
function WorkflowListController($scope, $location, $resource, workflow, items, navbar) {
  //Model: UI
  $scope.showItemsBar = true;
  $scope.showStatus = true;
  $scope.name = "Workflows";
  navbar.highlight("workflows");  

  $scope.showConnections = function(task_div) {
    jsPlumb.Defaults.Container = "entry";

    var selectedTask = _.find($scope.tasks, function(task) {
      if (task.id === parseInt(task_div.attr('id'))) {
        return task;
      }
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

  //Model: data
  $scope.count = 0;
  $scope.items = items.all;  // bind only to shrunken array
  
  $scope.selectedObject = function() {
    if (items.selected)
      return items.data[items.selected.id];
  };

  $scope.selectItem = function(index) {
    items.selectItem(index);
    $scope.selected = items.selected;

    // Prepare tasks
    wf = items.data[items.selected.id];
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
    console.log("Starting load")
    this.klass = $resource('/:tenantId/workflows/');
    this.klass.get({tenantId: $scope.auth.tenantId}, function(list, getResponseHeaders){
      console.log("Load returned");
      items.receive(list, function(item, key) {
        return {id: key, name: item.name, created: item.created, tenantId: item.tenantId}});
      $scope.count = items.count;
      console.log("Done loading")
    });
  }

  //Setup
  $scope.$watch('items.selectedIdx', function(newVal, oldVal, scope) {
    if (newVal !== null) scroll.toCurrent();
  });

  $scope.load();
}

function WorkflowController($scope, $resource, $routeParams, workflow, items, scroll) {
  $scope.showStatus = true;
  $scope.name = "Progress";

  $scope.items = items.all;

  $scope.selected = items.selected;

  $scope.refresh = function() {
    //items.getTasksFromServer();
  };

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

  $scope.percentComplete = function() {
    return (($scope.totalTime - $scope.timeRemaining) / $scope.totalTime) * 100;
  };

  $scope.selectItem = function(index) {
    items.selectItem(index);
    $scope.drawWorkflow;
  };
  
  $scope.drawWorkflow = function() {
    // Prepare tasks
    wf = items.data;  //TODO: fix this
    $scope.task_specs = wf.wf_spec.task_specs;
    $scope.tasks = workflow.flattenTasks({}, wf.task_tree);
    $scope.jit = workflow.parseTasks($scope.tasks, wf.wf_spec.task_specs);
    
    // Render tasks
    workflow.renderWorkflow('.entry', '#task', $scope.jit, $scope);
    $scope.selected = {name: wf.id, read: true, active: true};
  };

  $scope.handleSpace = function() {
    if (!scroll.pageDown()) {
      items.next();
    }
  };
  
  $scope.init_editor = function() {
    if ($scope.Editor !== undefined)
      return;
    $("#editor").text(JSON.stringify(items.data, null, "  "));
    var foldFunc = CodeMirror.newFoldFunction(CodeMirror.braceRangeFinder);
    $scope.Editor = CodeMirror.fromTextArea(document.getElementById('editor'), {
      theme: 'lesser-dark',
      mode: {name: "javascript", json: true},
      lineNumbers: true,
      onGutterClick: foldFunc,
      autoFocus: true,
      lineWrapping: true,
      dragDrop: false,
      matchBrackets: true
      });

  }

  $scope.load = function() {
    this.klass = $resource('/:tenantId/workflows/:id');
    this.klass.get($routeParams,
                   function(object, getResponseHeaders){
      items.data = object;
      items.tasks = workflow.flattenTasks({}, object.task_tree);
      items.all = workflow.parseTasks(items.tasks, object.wf_spec.task_specs);
      $scope.calculateStatistics(items.all);
      items.filtered = items.all;
      $scope.items = items.all;
      $scope.count = items.all.length;
      $scope.drawWorkflow();
      if ($scope.Editor !== undefined)
        Editor.setValue(JSON.stringify(object));
      if ($scope.taskStates.completed < $scope.count)
        setTimeout($scope.load, 2000);
    }, function(error) {
      console.log("Error " + error.data + "(" + error.status + ") loading workflow.");
      $scope.$root.error = {data: error.data, status: error.status, title: "Error loading workflow",
              message: "There was an error loading your workflow:"};
      $('#modalError').modal('show');
    });
  }
  
  $scope.$watch('items.selectedIdx', function(newVal, oldVal, scope) {
    if (newVal !== null) scroll.toCurrent();
  });
  $scope.load();

  $scope.calculateStatistics = function(tasks) {
    $scope.totalTime = 0;
    $scope.timeRemaining  = 0;
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
    _.each(tasks, function(task) {
      if ("internal_attributes" in task && "estimated_completed_in" in task["internal_attributes"]) {
        $scope.totalTime += parseInt(task["internal_attributes"]["estimated_completed_in"], 10);
      } else {
        $scope.totalTime += 10;
      };
      switch(task.state) {
        case 1:
          $scope.taskStates["future"] += 1;
          break;
        case 2:
          $scope.taskStates["likely"] += 1;
          break;
        case 4:
          $scope.taskStates["maybe"] += 1;
          break;
        case 8:
          $scope.taskStates["waiting"] += 1;
          break;
        case 16:
          $scope.taskStates["ready"] += 1;
          break;
        case 128:
          $scope.taskStates["triggered"] += 1;
          break;
        case 32:
          $scope.taskStates["cancelled"] += 1;
          break;
        case 64:
          $scope.taskStates["completed"] += 1;
          if ("internal_attributes" in task && "estimated_completed_in" in task["internal_attributes"]) {
            $scope.timeRemaining -= parseInt(task["internal_attributes"]["estimated_completed_in"], 10);
          } else {
            $scope.timeRemaining -= 10;
          }
          break;
        default:
          console.log("Invalid state '" + task.state + "'.");
      }
    });
    $scope.timeRemaining += $scope.totalTime;
  }

  $scope.showConnections = function(task_div) {
    jsPlumb.Defaults.Container = "task_container";

    var selectedTask = _.find($scope.tasks, function(task) {
      if (task.id === parseInt(task_div.attr('id'))) {
        return task;
      }
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

/**
 *   blueprints
 */
function BlueprintListController($scope, $location, $resource, items) {
  //Model: UI
  $scope.showSummaries = true;
  $scope.showStatus = false;

  $scope.items = items;
  $scope.name = '';
  $scope.count = 0;

  $scope.refresh = function() {
  };

  $scope.handleSpace = function() {
  };
  
  $scope.load = function() {
    console.log("Starting load")
    this.Blueprints = $resource('/:tenantId/blueprints/');
    this.Blueprints.get({tenantId: 557366}, function(blueprints, getResponseHeaders){
      $scope.items.receive(blueprints);
      $scope.name = $scope.items.name;
      $scope.count = $scope.items.count;
      console.log("Done loading")
    });
  }

  $scope.load_one = function() {
    this.Blueprint = $resource('/:tenantId/blueprints/:id');
    this.Blueprint.get({tenantId: $scope.auth.tenantId, id: $routeParams['id']}, function(blueprint, getResponseHeaders){
      $scope.items.all = [{id: blueprint.id, name: blueprint.name}];
      $scope.items.filtered = $scope.items.all;
    });
  }

}

/**
 *   deployments
 */
function DeploymentListController($scope, $location, $http, $resource, items) {
  //Model: UI
  $scope.showItemsBar = true;
  $scope.showStatus = true;
  $scope.name = "Deployments";
  
  //Model: data
  $scope.count = 0;
  $scope.items = items.all;  // bind only to shrunken array
  
  $scope.selectedObject = function() {
    if (items.selected)
      return items.data[items.selected.id];
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
    console.log("Starting load")
    this.klass = $resource('/:tenantId/deployments/');
    this.klass.get({tenantId: $scope.auth.tenantId}, function(list, getResponseHeaders){
      console.log("Load returned");
      items.receive(list, function(item) {
        return {id: item.id, name: item.name, created: item.created, tenantId: item.tenantId}});
      $scope.count = items.count;
      console.log("Done loading")
    });
  }

  //Setup
  $scope.$watch('items.selectedIdx', function(newVal, oldVal, scope) {
    if (newVal !== null) scroll.toCurrent();
  });

  $scope.load();
}

function DeploymentNewController($scope, $location, $routeParams, $resource, settings) {
  var ctrl = new DeploymentInitController($scope, $location, $routeParams, $resource, null, null, settings);
  return ctrl;
}

function DeploymentTryController($scope, $location, $routeParams, $resource, settings) {
  $scope.environments = [WPENV];
  $scope.blueprints = [WPBP];
  var ctrl = new DeploymentInitController($scope, $location, $routeParams, $resource, WPBP, WPENV, settings);
  $scope.updateSettings();
  return ctrl;
}

function DeploymentInitController($scope, $location, $routeParams, $resource, blueprint, environment, settings) {
  $scope.environment = environment;
  $scope.blueprint = blueprint;
  $scope.answers = {};

  $scope.updateSettings = function() {
    $scope.settings = [];
    $scope.answers = {};

    if ($scope.blueprint) {
      $scope.settings = $scope.settings.concat(settings.getSettingsFromBlueprint($scope.blueprint));
    }

    if ($scope.environment) {
      $scope.settings = $scope.settings.concat(settings.getSettingsFromEnvironment($scope.environment));
    }

    _.each($scope.settings, function(setting) {
      if ('default' in setting) {
        $scope.answers[setting.id] = setting['default'];
      } else
        $scope.answers[setting.id] = null;
    });
  };

  // Display settings using templates for each type
  $scope.renderSetting = function(setting) {
    if (!setting) {
      var message = "The requested setting is null";
      console.log(message);
      return "<em>" + message + "</em>";
    }

    if (!setting.type || !_.isString(setting.type)) {
      var message = "The requested setting '" + setting.id + "' has no type or the type is not a string.";
      console.log(message);
      return "<em>" + message + "</em>";
    }
    var lowerType = setting.type.toLowerCase().trim();
    if (lowerType == "select") {
      if ("choice" in setting) {
        if (!_.isString(setting.choice[0]))
          lowerType = lowerType + "-kv";
        }
      }
    var template = $('#setting-' + lowerType).html();

    if (template === null) {
      var message = "No template for setting type '" + setting.type + "'.";
      console.log(message);
      return "<em>" + message + "</em>";
    }
      return (template ? Mustache.render(template, setting) : "").trim();
  };

  $scope.showSettings = function() {
    return ($scope.environment && $scope.blueprint);
  };

  $scope.submit = function(simulate) {
    var deployment = {};

    deployment.blueprint = $scope.blueprint;
    deployment.environment = $scope.environment;
    deployment.inputs = {};
    deployment.inputs.blueprint = {};
    deployment.tenantId = $scope.auth.tenantId;

    // Have to fix some of the answers so they are in the right format, specifically the select
    // and checkboxes. This is lame and slow and I should figure out a better way to do this.
    _.each($scope.answers, function(element, key) {
      var setting = _.find($scope.settings, function(item) {
        if (item.id == key) {
          return item;
        }
      });

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
  };

  $scope.simulate = function() {
    var Deployment = $resource('/:tenantId/deployments/simulate', {tenantId: $scope.auth.tenantId});
    var deployment = new Deployment({});
    deployment.blueprint = $scope.blueprint;
    deployment.environment = $scope.environment;
    deployment.inputs = {};
    deployment.inputs.blueprint = {};

    // Have to fix some of the answers so they are in the right format, specifically the select
    // and checkboxes. This is lame and slow and I should figure out a better way to do this.
    _.each($scope.answers, function(element, key) {
      var setting = _.find($scope.settings, function(item) {
        if (item.id == key) {
          return item;
        }
      });

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

    if ($scope.auth.loggedIn) {
        deployment.$save(function(returned, getHeaders){
        var deploymentId = getHeaders('location').split('/')[3];
        console.log("Posted deployment", deploymentId);
        $location.path('/' + $scope.auth.tenantId + '/workflows/' + deploymentId);
      }, function(error) {
        console.log("Error " + error.data + "(" + error.status + ") creating new deployment.");
        console.log(deployment);
        $scope.$root.error = {data: error.data, status: error.status, title: "Error Creating Deployment",
                message: "There was an error creating your deployment:"};
        $('#modalError').modal('show');
      });
    } else {
      $scope.loginPrompt(); //TODO: implement a callback
    }
  };

  // Load blueprints
  if (!blueprint) {
    $scope.signIn();
    cm.Resource.query($http, $scope, 'blueprints').success(function(data) {
      $scope.blueprints = data;

      if ($routeParams.blueprintId) {
        $scope.blueprint = _.find($scope.blueprints, function(bp) {
          return bp.id == $routeParams.blueprintId;
        });
        $scope.updateSettings();
      }
    });
  }

  // Load the environments
  if (!environment) {
    $scope.signIn();
    cm.Resource.query($http, $scope, 'environments').success(function(data) {
      $scope.environments = data;
    });
  }
}

/*
 * other stuff
 */
document.addEventListener('DOMContentLoaded', function(e) {
  //On mobile devices, hide the address bar
  window.scrollTo(0);
}, false);

//Initial Wordpress Template
WPBP = {
        "description": "Create a multi-server WordPress deployment on any cloud account using the Chef cookbooks created by the Managed Cloud team.",
        "services": {
            "lb": {
                "open-ports": [
                    "80/tcp"
                ],
                "component": {
                    "interface": "http",
                    "type": "load-balancer"
                },
                "relations": {
                    "web": "http",
                    "master": "http"
                },
                "exposed": true
            },
            "master": {
                "component": {
                    "type": "application",
                    "role": "master",
                    "name": "wordpress"
                },
                "relations": {
                    "backend": "mysql"
                },
                "constraints": [
                    {
                        "count": 1
                    }
                ]
            },
            "web": {
                "component": {
                    "type": "application",
                    "role": "web",
                    "name": "wordpress",
                    "options": [
                        {
                            "wordpress/version": "3.0.4"
                        }
                    ]
                },
                "relations": {
                    "master": "http",
                    "db": {
                        "interface": "mysql",
                        "service": "backend"
                    }
                }
            },
            "backend": {
                "component": {
                    "interface": "mysql",
                    "type": "database"
                }
            }
        },
        "options": {
            "domain": {
                "regex": "^(([a-zA-Z]|[a-zA-Z][a-zA-Z0-9\\-]*[a-zA-Z0-9])\\.)*([A-Za-z]|[A-Za-z][A-Za-z0-9\\-]*[A-Za-z0-9])$",
                "constrains": [
                    {
                        "setting": "apache/domain_name",
                        "service": "web",
                        "resource_type": "application"
                    }
                ],
                "description": "The domain you wish to host your blog on. (ex: example.com)",
                "label": "Domain",
                "sample": "example.com",
                "type": "string"
            },
            "path": {
                "constrains": [
                    {
                        "setting": "apache/path",
                        "service": "web",
                        "resource_type": "application"
                    },
                    {
                        "setting": "path",
                        "service": "web",
                        "resource_type": "application"
                    }
                ],
                "description": "The path you wish to host your blog on under your domain. (ex: /blog)",
                "default": "/",
                "label": "Path",
                "sample": "/blog",
                "type": "string"
            },
            "register-dns": {
                "default": false,
                "type": "boolean",
                "label": "Register DNS Name"
            },
            "region": {
                "required": true,
                "type": "select",
                "default": "DFW",
                "label": "Region",
                "choice": [{
                    "name": "dallas", "value": "DFW"},
                    {"name": "chicago", "value": "ORD"}
                ]
            },
            "prefix": {
                "constrains": [
                    {
                        "setting": "database/prefix",
                        "service": "web",
                        "resource_type": "application"
                    },
                    {
                        "setting": "user/name",
                        "service": "web",
                        "resource_type": "application"
                    },
                    {
                        "setting": "apache/user/name",
                        "service": "web",
                        "resource_type": "application"
                    },
                    {
                        "setting": "lsyncd/user/name",
                        "service": "web",
                        "resource_type": "application"
                    },
                    {
                        "setting": "database/name",
                        "service": "backend",
                        "resource_type": "database"
                    },
                    {
                        "setting": "database/username",
                        "service": "backend",
                        "resource_type": "database"
                    }
                ],
                "help": "Note that this also the user name, database name, and also identifies this\nwordpress install from other ones you might add later to the same deployment.\n",
                "default": "wp",
                "required": true,
                "label": "Prefix",
                "type": "string",
                "description": "The application ID (and wordpress table prefix)."
            },
            "password": {
                "type": "string",
                "description": "Password to use for service. Click the generate button to generate a random password.",
                "label": "Password"
            },
            "os": {
                "constrains": [
                    {
                        "setting": "os",
                        "service": "web",
                        "resource_type": "compute"
                    },
                    {
                        "setting": "os",
                        "service": "web",
                        "resource_type": "compute"
                    }
                ],
                "description": "The operating system for the web servers.",
                "default": "Ubuntu 12.04",
                "label": "Operating System",
                "type": "select",
                "choice": [
//                    "Ubuntu 11.10",
                    "Ubuntu 12.04",
//                    "CentOS",
//                    "RHEL 6"
                ]
            },
            "web_server_size": {
                "constrains": [
                    {
                        "setting": "size",
                        "service": "web",
                        "resource_type": "compute"
                    },
                    {
                        "setting": "size",
                        "service": "master",
                        "resource_type": "compute"
                    }
                ],
                "description": "The size of the instance in MB of RAM.",
                "default": 1024,
                "label": "Web Server Size",
                "type": "select",
                "choice": [
                    {
                        "name": "512 Mb",
                        "value": 512
                    },
                    {
                        "name": "1 Gb",
                        "value": 1024
                    },
                    {
                        "name": "2 Gb",
                        "value": 2048
                    }
                ]
            },
            "web_server_count": {
                "constrains": [
                    {
                        "setting": "count",
                        "service": "web",
                        "resource_type": "compute"
                    }
                ],
                "description": "The number of WordPress servers (minimum two).",
                "default": 2,
                "label": "Number of Web Servers",
                "type": "int",
                "constraints": [
                    {
                        "greater-than": 1
                    }
                ]
            },
            "database_memory": {
                "constrains": [
                    {
                        "setting": "memory",
                        "service": "backend",
                        "resource_type": "database"
                    }
                ],
                "description": "The size of the database instance in MB of RAM.",
                "default": 512,
                "label": "Database Size",
                "type": "select",
                "choice": [
                    {
                        "name": "512 Mb",
                        "value": 512
                    },
                    {
                        "name": "1024 Mb",
                        "value": 1024
                    },
                    {
                        "name": "2048 Mb",
                        "value": 2048
                    },
                    {
                        "name": "4096 Mb",
                        "value": 4096
                    }
                ]
            },
            "database_volume_size": {
                "default": 1,
                "constrains": [
                    {
                        "setting": "disk",
                        "service": "backend",
                        "resource_type": "database"
                    }
                ],
                "type": "int",
                "description": "The hard drive space available for the database instance in GB.",
                "label": "Database Disk Size"
            },
            "varnish": {
                "default": false,
                "constrains": [
                    {
                        "setting": "varnish/enabled",
                        "service": "web",
                        "resource_type": "application"
                    }
                ],
                "type": "boolean",
                "label": "Varnish Caching"
            },
            "ssl": {
                "default": false,
                "label": "SSL Enabled",
                "type": "boolean",
                "help": "If this option is selected, SSL keys need to be supplied as well. This option is\nalso currently mutually exclusive with the Varnish Caching option.\n",
                "description": "Use SSL to encrypt web traffic."
            },
            "ssl_certificate": {
                "sample": "-----BEGIN CERTIFICATE-----\nEncoded Certificate\n-----END CERTIFICATE-----\n",
                "constrains": [
                    {
                        "setting": "apache/ssl_certificate",
                        "service": "web",
                        "resource_type": "application"
                    }
                ],
                "type": "text",
                "description": "SSL certificate in PEM format. Make sure to include the BEGIN and END certificate lines.",
                "label": "SSL Certificate"
            },
            "ssl_private_key": {
                "sample": "-----BEGIN PRIVATE KEY-----\nEncoded key\n-----END PRIVATE KEY-----\n",
                "constrains": [
                    {
                        "setting": "apache/ssl_private_key",
                        "service": "web",
                        "resource_type": "application"
                    }
                ],
                "type": "string",
                "label": "SSL Certificate Private Key"
            }
        },
        "name": "Managed Cloud WordPress"
    };
//Default Environment
WPENV = {
        "description": "This environment tests legacy cloud servers. It is hard-targetted at chicago\nbecause the rackcloudtech legacy servers account is in chicago\n",
        "name": "Legacy Cloud Servers",
        "providers": {
            "legacy": {
                "catalog": {
                    "compute": {
                        "windows_instance": {
                            "is": "compute",
                            "id": "windows_instance",
                            "provides": [
                                {
                                    "compute": "windows"
                                }
                            ]
                        },
                        "linux_instance": {
                            "is": "compute",
                            "id": "linux_instance",
                            "provides": [
                                {
                                    "compute": "linux"
                                }
                            ]
                        }
                    },
                    "lists": {
                        "types": {
                            "24": {
                                "os": "Windows Server 2008 SP2 (64-bit)",
                                "name": "Windows Server 2008 SP2 (64-bit)"
                            },
                            "115": {
                                "os": "Ubuntu 11.04",
                                "name": "Ubuntu 11.04"
                            },
                            "31": {
                                "os": "Windows Server 2008 SP2 (32-bit)",
                                "name": "Windows Server 2008 SP2 (32-bit)"
                            },
                            "56": {
                                "os": "Windows Server 2008 SP2 (32-bit) + SQL Server 2008 R2 Standard",
                                "name": "Windows Server 2008 SP2 (32-bit) + SQL Server 2008 R2 Standard"
                            },
                            "120": {
                                "os": "Fedora 16",
                                "name": "Fedora 16"
                            },
                            "121": {
                                "os": "CentOS 5.8",
                                "name": "CentOS 5.8"
                            },
                            "122": {
                                "os": "CentOS 6.2",
                                "name": "CentOS 6.2"
                            },
                            "116": {
                                "os": "Fedora 15",
                                "name": "Fedora 15"
                            },
                            "125": {
                                "os": "Ubuntu 12.04 LTS",
                                "name": "Ubuntu 12.04 LTS"
                            },
                            "126": {
                                "os": "Fedora 17",
                                "name": "Fedora 17"
                            },
                            "119": {
                                "os": "Ubuntu 11.10",
                                "name": "Ubuntu 11.10"
                            },
                            "118": {
                                "os": "CentOS 6.0",
                                "name": "CentOS 6.0"
                            }
                        },
                        "sizes": {
                            "3": {
                                "disk": 40,
                                "name": "1GB server",
                                "memory": 1024
                            },
                            "2": {
                                "disk": 20,
                                "name": "512 server",
                                "memory": 512
                            },
                            "5": {
                                "disk": 160,
                                "name": "4GB server",
                                "memory": 4096
                            },
                            "4": {
                                "disk": 80,
                                "name": "2GB server",
                                "memory": 2048
                            },
                            "7": {
                                "disk": 620,
                                "name": "15.5GB server",
                                "memory": 15872
                            },
                            "6": {
                                "disk": 320,
                                "name": "8GB server",
                                "memory": 8192
                            },
                            "8": {
                                "disk": 1200,
                                "name": "30GB server",
                                "memory": 30720
                            }
                        }
                    }
                },
                "vendor": "rackspace",
                "provides": [
                    {
                        "compute": "linux"
                    },
                    {
                        "compute": "windows"
                    }
                ]
            },
            "chef-local": {
                "vendor": "opscode",
                "provides": [
                    {
                        "application": "http"
                    },
                    {
                        "database": "mysql"
                    }
                ]
            },
            "common": {
                "vendor": "rackspace"
            },
            "load-balancer": {
                "catalog": {
                    "lists": {
                        "regions": {
                            "DFW": "https://dfw.loadbalancers.api.rackspacecloud.com/v1.0/",
                            "ORD": "https://ord.loadbalancers.api.rackspacecloud.com/v1.0/"
                        }
                    },
                    "load-balancer": {
                        "http": {
                            "is": "load-balancer",
                            "id": "http",
                            "provides": [
                                {
                                    "load-balancer": "http"
                                }
                            ],
                            "options": "ref://id001"
                        },
                        "https": {
                            "is": "load-balancer",
                            "id": "https",
                            "provides": [
                                {
                                    "load-balancer": "https"
                                }
                            ],
                            "options": "ref://id001"
                        }
                    }
                },
                "endpoint": "https://lbaas.api.rackpsacecloud.com/loadbalancers/",
                "vendor": "rackspace",
                "provides": [
                    {
                        "load-balancer": "http"
                    }
                ]
            },
            "database": {
                "catalog": {
                    "compute": {
                        "mysql_instance": {
                            "is": "compute",
                            "id": "mysql_instance",
                            "provides": [
                                {
                                    "compute": "mysql"
                                }
                            ],
                            "options": {
                                "disk": {
                                    "type": "int",
                                    "unit": "Gb",
                                    "choice": [
                                        1,
                                        2,
                                        3,
                                        4,
                                        5,
                                        6,
                                        7,
                                        8,
                                        9,
                                        10
                                    ]
                                },
                                "memory": {
                                    "type": "int",
                                    "unit": "Mb",
                                    "choice": [
                                        512,
                                        1024,
                                        2048,
                                        4096
                                    ]
                                }
                            }
                        }
                    },
                    "lists": {
                        "regions": {
                            "DFW": "https://dfw.databases.api.rackspacecloud.com/v1.0/557366",
                            "ORD": "https://ord.databases.api.rackspacecloud.com/v1.0/557366"
                        },
                        "sizes": {
                            "1": {
                                "name": "m1.tiny",
                                "memory": 512
                            },
                            "3": {
                                "name": "m1.medium",
                                "memory": 2048
                            },
                            "2": {
                                "name": "m1.small",
                                "memory": 1024
                            },
                            "4": {
                                "name": "m1.large",
                                "memory": 4096
                            }
                        }
                    },
                    "database": {
                        "mysql_database": {
                            "is": "database",
                            "requires": [
                                {
                                    "compute": {
                                        "interface": "mysql",
                                        "relation": "host"
                                    }
                                }
                            ],
                            "id": "mysql_database",
                            "provides": [
                                {
                                    "database": "mysql"
                                }
                            ]
                        }
                    }
                },
                "vendor": "rackspace",
                "provides": [
                    {
                        "database": "mysql"
                    },
                    {
                        "compute": "mysql"
                    }
                ]
            }
        }
    };
