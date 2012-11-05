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
    template: '<calculator/>',
    controller: StaticController
  })

  // Legacy Paths - none of these should be in use anymore
  $routeProvider.
  when('/:tenantId/environments/:id', {
    controller: LegacyController,
    template:'<section class="entries" ng-include="templateUrl"><img src="/static/img/ajax-loader-bar.gif" alt="Loading..."/></section>'
  }).
  when('/:tenantId/workflows/:id/legacy', {
    controller: LegacyController,
    template:'<section class="entries" ng-include="templateUrl"><img src="/static/img/ajax-loader-bar.gif" alt="Loading..."/></section>'
  }).
  when('/:tenantId/workflows/:id/tasks/:task_id', {
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
  when('/:tenantId/workflows/:id/status', {
    templateUrl: '/static/ui/partials/workflow_status.html',
    controller: WorkflowController
  }).
  when('/:tenantId/workflows/:id', {
    templateUrl: '/static/ui/partials/workflow.html',
    controller: WorkflowController,
    reloadOnSearch: false
  }).
  when('/:tenantId/workflows', {
    templateUrl: '/static/ui/partials/workflows.html',
    controller: WorkflowListController,
  }).
  when('/:tenantId/blueprints/:id', {
    templateUrl: '/static/ui/partials/level2.html',
    controller: BlueprintListController
  }).
  when('/:tenantId/blueprints', {
    templateUrl: '/static/ui/partials/blueprints.html',
    controller: BlueprintListController
  }).
  when('/:tenantId/deployments', {
    templateUrl: '/static/ui/partials/deployments.html',
    controller: DeploymentListController
  }).
  when('/:tenantId/deployments/:id', {
    controller: DeploymentController,
    templateUrl: '/static/ui/partials/deployment.html'
  }).
  when('/:tenantId/providers', {
    controller: ProviderListController,
    templateUrl: '/static/ui/partials/providers.html'
  }).
  when('/:tenantId/environments', {
    controller: EnvironmentListController,
    templateUrl: '/static/ui/partials/environments.html'
  }).
  otherwise({
    controller: ExternalController,
    template:'<section class="entries" ng-include="templateUrl"><img src="/static/img/ajax-loader-bar.gif" alt="Loading..."/></section>',
    reloadOnSearch: false
  });  //normal browsing
  
  
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

//Loads the old ui (rendered at the server)
function LegacyController($scope, $location, $routeParams, $resource, navbar, $window, $http) {
  $scope.showHeader = false;
  $scope.showStatus = false;
  var parts = $location.path().split('/')
  if (parts.length > 1)
    navbar.highlight(parts[2]);

  var path;
  if ('tenantId' in $routeParams) {
    path = $location.path();
  } else if ($location.path().indexOf('/' + $scope.$parent.auth.tenantId + '/') == 0) {
    path = $location.path();
  } else {
    path = '/' + $scope.$parent.auth.tenantId + $location.path();
  }
  if (path.indexOf(".html") == -1 )
    path += ".html";
  if ($location.url().length > $location.path().length)
    path += $location.url().substr($location.path().length);
  console.log("Legacy controller loading " + path);
  $scope.templateUrl = path;

  $scope.save = function() {
    if ($scope.auth.loggedIn) {
      var klass = $resource($location.path());
      var thang = new klass(JSON.parse(Editor.getValue()));
      thang.$save(function(returned, getHeaders){
          $scope.notify('Saved');
        }, function(error) {
          $scope.$root.error = {data: error.data, status: error.status, title: "Error Saving",
                  message: "There was an error saving your JSON:"};
          $('#modalError').modal('show');
        });
    } else {
      $scope.loginPrompt($scope.save); //TODO: implement a callback
    }
  };

  $scope.action = function(action) {
    if ($scope.auth.loggedIn) {
      console.log("Executing action " + $location.path() + '/' + action)
      $http({method: 'POST', url: $location.path() + '/' + action}).
        success(function(data, status, headers, config) {
          $scope.notify("Command '" + action.replace('+', '') + "' executed");
          // this callback will be called asynchronously
          // when the response is available
          $window.location.reload();
        });
    } else {
      $scope.loginPrompt(); //TODO: implement a callback
    }
  };

  $scope.target_action = function(target) {
    if ($scope.auth.loggedIn) {
      console.log("Executing action " + target)
      $http({method: 'POST', url: target}).
        success(function(data, status, headers, config) {
          $scope.notify("Command '" + _.last(target.split("/")).replace('+', '') + "' executed");
          // this callback will be called asynchronously
          // when the response is available
          $window.location.reload();
        });
    } else {
      $scope.loginPrompt(); //TODO: implement a callback
    }
  };

}

//Root controller that implements authentication
function AppController($scope, $http, $location) {
  $scope.showHeader = true;
  $scope.showStatus = false;
  $scope.auth = {
      username: '',
      tenantId: '',
      expires: ''
    };

  $scope.navigate = function(url) {
    $location.path(url);
  }

  $scope.notify = function(message) {
    $('.bottom-right').notify({
        message: { text: message }, fadeOut: {enabled: true, delay: 5000},
        type: 'bangTidy'
      }).show();
  }

  //Accepts subset of auth data. We user a subset so we can store it locally.
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
      WPBP.DBaaS.options.region.default = response.access.user['RAX-AUTH:defaultRegion'] || response.access.regions[0];
      WPBP.DBaaS.options.region.choice = response.access.regions;
      WPBP.MySQL.options.region.default = WPBP.DBaaS.options.region.default;
      WPBP.MySQL.options.region.choice = WPBP.DBaaS.options.region.choice;
  }

  // Restore login from session
  var auth = localStorage.getItem('auth');
  if (auth != undefined && auth !== null)
    auth = JSON.parse(auth);
  if (auth != undefined && auth !== null && auth != {} && 'access' in auth) {
      $scope.accept_auth_data(auth);
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

    if (auth_url === undefined || auth_url === null || auth_url.length == 0) {
      headers = {};  // Not supported on server, but we should do it
    } else {
      headers = {"X-Auth-Source": auth_url};
    }
    return $.ajax({
      type: "POST",
      contentType: "application/json; charset=utf-8",
      headers: headers,
      dataType: "json",
      url: "/authproxy",
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


  // Utility Functions

  //Check for a supported account
  $scope.is_unsupported_account = function() {
    roles = [];
    if ($scope.auth.loggedIn === true)
        $scope.auth.catalog.access.user.roles || []
    return _.any(roles, function(role) {return role.name == "rack_connect"});
  }

  $scope.generatePassword = function() {
      if (parseInt(navigator.appVersion) <= 3) {
          $scope.notify("Sorry this only works in 4.0+ browsers");
          return true;
      }

      var length=10;
      var sPassword = "";

      var noPunction = true;
      for (i=0; i < length; i++) {

          var numI = $scope.getPwdRandomNum();
          //Always have a letter for the first character.
          while (i==0 && (numI <= 64 || ((numI >=91) && (numI <=96)))) { numI = $scope.getPwdRandomNum(); }
          //Only allow letters and numbers for all other characters.
          while (((numI >=58) && (numI <=64)) || ((numI >=91) && (numI <=96))) { numI = $scope.getPwdRandomNum(); }

          sPassword = sPassword + String.fromCharCode(numI);
      }
      return sPassword;
  }

  $scope.getPwdRandomNum = function() {

      // between 0 - 1
      var rndNum = Math.random()

      // rndNum from 0 - 1000
      rndNum = parseInt(rndNum * 1000);

      // rndNum from 33 - 127
      rndNum = (rndNum % 75) + 48;

      return rndNum;
  }
}

function NavBarController($scope, $location, $resource) {
  $scope.feedback = "";
  $scope.email = "";
  console.log("Getting api version");
  this.api = $resource('/version');
  this.api.get(function(data, getResponseHeaders){
	  $scope.api_version = data.version;
	  console.log("Got version: " + $scope.api_version);
  });

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
            "api_version": $scope.api_version
            }
          });
    headers = checkmate.config.header_defaults.headers.common;
    return $.ajax({
      type: "POST",
      contentType: "application/json; charset=utf-8",
      headers: headers,
      dataType: "json",
      url: "/feedback",
      data: data
    }).success(function(json) {
        $('.dropdown.open .dropdown-toggle').dropdown('toggle');
        $scope.notify("Feedback received. Thank you!");
        $scope.feedback = "";
        $("#feedback_error").hide();
    }).error(function(response) {
      $("#feedback_error_text").html(response.statusText);
      $("#feedback_error").show();
    });
  }

}

//Workflow controllers
function WorkflowListController($scope, $location, $resource, workflow, items, navbar) {
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
    console.log("Starting load")
    this.klass = $resource('/:tenantId/workflows/.json');
    this.klass.get({tenantId: $scope.auth.tenantId}, function(list, getResponseHeaders){
      console.log("Load returned");
      items.receive(list, function(item, key) {
        return {id: key, name: item.wf_spec.name, tenantId: item.tenantId}});
      $scope.count = items.count;
      $scope.items = items.all;
      console.log("Done loading")
    });
  }

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
    this.klass = $resource('/:tenantId/workflows/:id');
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
          var d = $resource('/:tenantId/deployments/:id');
          d.get($routeParams,
                         function(object, getResponseHeaders){
            var domain = null;
            //Find domain in inputs
            try {
              domain = object.inputs.blueprint.domain;
            }
            catch (error) {
              console.log(error);
            }
            //If no domain, use load-balancer VIP
            if (domain === null) {
              try {
                var lb = _.find(object.resources, function(r, k) { return r.type == 'load-balancer';});
                if ('instance' in lb) {
                  domain = lb.instance.vip;
                }
              }
              catch (error) {
                console.log(error);
              }
            }
            //Find path in inputs
            var path = "/";
            try {
              path = object.inputs.blueprint.path;
            }
            catch (error) {
              console.log(error);
            }
            $scope.data.output = {};
            $scope.data.output.path = "http://" + domain + path;
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
        $scope.selectSpec(Object.keys(object.wf_spec.task_specs)[0]);
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
  }
  
  //Parse loaded workflow
  $scope.parse = function(object) {
      $scope.data = object;
      items.tasks = workflow.flattenTasks({}, object.task_tree);
      items.all = workflow.parseTasks(items.tasks, object.wf_spec.task_specs);
      $scope.count = items.all.length;
      workflow.calculateStatistics($scope, items.all);
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
      })
    $scope.current_spec_tasks = tasks;
    tasks = $scope.spec_tasks(spec_id);
    if (tasks && !(_.include(tasks, $scope.current_task))) 
      $scope.selectTask(tasks[0].id);
    $scope.toCurrent();
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
            };
    }, 0);
  }
  
  $scope.state_class = function(task) {
    return workflow.classify(task);
  }

  $scope.state_name = function(task) {
    return workflow.state_name(task);
  }
  
  $scope.save_spec = function() {
    var editor = _.find($('.CodeMirror'), function(c) {
      return c.CodeMirror.getTextArea().id == 'spec_source';
      });

    if ($scope.auth.loggedIn) {
      var klass = $resource('/:tenantId/workflows/:id/specs/' + $scope.current_spec_index);
      var thang = new klass(JSON.parse(editor.CodeMirror.getValue()));
      thang.$save($routeParams, function(returned, getHeaders){
          // Update model
          for (var attr in returned) {
            if (returned.hasOwnProperty(attr))
              $scope.current_spec[attr] = returned[attr];
          };
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
    } catch(err) {};
    // Refresh CodeMirror since it might have been hidden
    $('.CodeMirror')[1].CodeMirror.refresh();
  };

  $scope.save_task = function() {
    var editor = _.find($('.CodeMirror'), function(c) {
      return c.CodeMirror.getTextArea().id == 'task_source';
      });

    if ($scope.auth.loggedIn) {
      var klass = $resource('/:tenantId/workflows/:id/tasks/' + $scope.current_task_index);
      var thang = new klass(JSON.parse(editor.CodeMirror.getValue()));
      thang.$save($routeParams, function(returned, getHeaders){
          // Update model
          for (var attr in returned) {
            if (['workflow_id', "tenantId"].indexOf(attr) == -1 && returned.hasOwnProperty(attr))
              $scope.current_task[attr] = returned[attr];
          };
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
  }

  $scope.reset_task = function() {
    return $scope.task_action($scope.current_task.id, 'reset');
  }

  $scope.resubmit_task = function() {
    return $scope.task_action($scope.current_task.id, 'resubmit');
  }

  $scope.was_server_created = function() {
    if (typeof $scope.current_task != 'undefined' && ($scope.current_task.task_spec.indexOf("Create Server") == 0 || $scope.current_task.task_spec.indexOf("Wait for Server") == 0) &&
        $scope.resource($scope.current_task) !== null)
      return true;
    return false;
  }

  $scope.was_database_created = function() {
    if (typeof $scope.current_task != 'undefined' && ($scope.current_task.task_spec.indexOf("Create Database") == 0 || $scope.current_task.task_spec.indexOf("Add DB User") == 0) &&
        $scope.resource($scope.current_task) !== null)
      return true;
    return false;
  }

  $scope.was_loadbalancer_created = function() {
    if (typeof $scope.current_task != 'undefined' && $scope.current_task.task_spec.indexOf("Create L") == 0 &&
        $scope.resource($scope.current_task) !== null)
      return true;
    return false;
  }

  $scope.resource = function(task) {
    if (typeof task == 'undefined')
      return null;
    try {
      var res = _.find(task.attributes, function(obj, attr) {
        if (attr.indexOf("instance:") == 0)
          return true;
        return false;
      });
  
      if (typeof res != "undefined")
        return res;
      return null;
    } catch(err) {
      console.log("Error in WorkflowController.resource: " + err);
    }
  }

  //Init
  if (!$scope.auth.loggedIn) {
      $scope.loginPrompt($scope.load);
  } else if ($location.path().split('/').slice(-1)[0] == '+preview') {
    $scope.parse(workflow.preview['workflow']);
  } else
    $scope.load();

  //Not real code. Just testing stuff
  $scope.showConnections = function(task_div) {
    jsPlumb.Defaults.Container = "entry";

    var selectedTask = _.find($scope.tasks, function(task) {
      if (task.id === parseInt(task_div.attr('id')))
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
    h = 500

    var vis = d3.select(".entries").append("svg:svg")
        .attr("width", w)
        .attr("height", h);
    var links = _.each($scope.data.wf_spec.task_specs, function(t, k) {return {"source": k, "target": "Root"};});
    var nodes = _.each($scope.data.wf_spec.task_specs, function(t, k) {return t;});
    
    var force = self.force = d3.layout.force()
        .nodes(nodes)
        .links(links)
        .gravity(.05)
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
        force.stop() // stops the force auto positioning before you start dragging
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
        .text(function(d) { return d.name });

    force.on("tick", tick);

    function tick() {
      link.attr("x1", function(d) { return d.source.x; })
          .attr("y1", function(d) { return d.source.y; })
          .attr("x2", function(d) { return d.target.x; })
          .attr("y2", function(d) { return d.target.y; });

      node.attr("transform", function(d) { return "translate(" + d.x + "," + d.y + ")"; });
    };

  };

  // Old code we might reuse
  $scope.showConnections = function(task_div) {
    jsPlumb.Defaults.Container = "task_container";

    var selectedTask = _.find($scope.tasks, function(task) {
      if (task.id === parseInt(task_div.attr('id')))
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
function BlueprintListController($scope, $location, $resource, items) {
  //Model: UI
  $scope.showSummaries = true;
  $scope.showStatus = false;

  $scope.name = 'Blueprints';
  $scope.count = 0;
  items.all = [];
  $scope.items = items.all;  // bind only to shrunken array

  $scope.refresh = function() {
  };

  $scope.handleSpace = function() {
  };
  
  $scope.load = function() {
    console.log("Starting load")
    this.klass = $resource('/:tenantId/blueprints/.json');
    this.klass.get({tenantId: $scope.auth.tenantId}, function(list, getResponseHeaders){
      console.log("Load returned");
      items.receive(list, function(item, key) {
        return {id: key, name: item.name, tenantId: item.tenantId}});
      $scope.count = items.count;
      $scope.items = items.all;
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

  //Setup
  $scope.$watch('items.selectedIdx', function(newVal, oldVal, scope) {
    if (newVal !== null) scroll.toCurrent();
  });

  $scope.load();
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
    console.log("Starting load")
    this.klass = $resource('/:tenantId/deployments/.json');
    this.klass.get({tenantId: $scope.auth.tenantId}, function(list, getResponseHeaders){
      console.log("Load returned");
      items.all = [];
      items.receive(list, function(item) {
        return {id: item.id, name: item.name, created: item.created, tenantId: item.tenantId,
                blueprint: item.blueprint, environment: item.environment,
                status: item.status}});
      $scope.count = items.count;
      $scope.items = items.all;
      console.log("Done loading")
    });
  }

  //Setup
  $scope.$watch('items.selectedIdx', function(newVal, oldVal, scope) {
    if (newVal !== null) scroll.toCurrent();
  });

  $scope.load();
}

function DeploymentNewController($scope, $location, $routeParams, $resource, settings, workflow) {
  var ctrl = new DeploymentInitController($scope, $location, $routeParams, $resource, null, null, settings, workflow);
  return ctrl;
}

function DeploymentTryController($scope, $location, $routeParams, $resource, settings, workflow) {
  $scope.environments = ENVIRONMENTS;
  $scope.blueprints = WPBP;
  var ctrl = new DeploymentInitController($scope, $location, $routeParams, $resource, WPBP['DBaaS'], ENVIRONMENTS['next-gen'], settings, workflow);
  $scope.updateSettings();
  $scope.updateDatabaseProvider();
  return ctrl;
}

function DeploymentInitController($scope, $location, $routeParams, $resource, blueprint, environment, settings, workflow) {
  $scope.environment = environment;
  $scope.blueprint = blueprint;
  $scope.answers = {};
  $scope.domain_names = [];

  //Retrieve existing domains  
  $scope.getDomains = function(){
    $scope.domain_names = [];
    if ($scope.auth.loggedIn){
      var tenant_id = $scope.auth.tenantId;
      url = '/:tenantId/providers/rackspace.dns/proxy/v1.0/'+tenant_id+'/domains';
      var Domains = $resource(url, {tenantId: $scope.auth.tenantId});            
      var domains = Domains.query(function() {
        var temp
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
  $scope.getDomains();

  $scope.onBlueprintChange = function() {
    $scope.updateSettings();
    $scope.updateDatabaseProvider();
  }

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
  }

  $scope.updateSettings = function() {
    $scope.settings = [];
    $scope.answers = {};

    if ($scope.blueprint) {
      $scope.settings = $scope.settings.concat(settings.getSettingsFromBlueprint($scope.blueprint));
    }

    if ($scope.environment) {
      $scope.settings = $scope.settings.concat(settings.getSettingsFromEnvironment($scope.environment));
      if ('legacy' in $scope.environment.providers) {
        if ($scope.settings && $scope.auth.loggedIn == true && 'RAX-AUTH:defaultRegion' in $scope.auth.catalog.access.user) {
            _.each($scope.settings, function(setting) {
                if (setting.id == 'region') {
                    setting.default = $scope.auth.catalog.access.user['RAX-AUTH:defaultRegion'];
                    setting.choice = [setting.default];
                    setting.description = "Your legacy cloud servers region is '" + setting.default + "'. You must deploy to this region";
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
    });
  };

  // Display settings using templates for each type
  $scope.renderSetting = function(setting) {
    //console.log("RENDERING");
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
      var message = "No template for setting type '" + setting.type + "'.";
      console.log(message);
      return "<em>" + message + "</em>";
    }
      return (template ? Mustache.render(template, setting) : "").trim();
  };

  $scope.showSettings = function() {
    return ($scope.environment && $scope.blueprint);
  };

  $scope.submit = function(action) {
    var url = '/:tenantId/deployments';
    if ((action !== undefined) && action)
      url += '/' + action;
    var Deployment = $resource(url, {tenantId: $scope.auth.tenantId});
    var deployment = new Deployment({});
    deployment.blueprint = $scope.blueprint;
    deployment.environment = $scope.environment;
    deployment.inputs = {};
    deployment.inputs.blueprint = {};

    // Have to fix some of the answers so they are in the right format, specifically the select
    // and checkboxes. This is lame and slow and I should figure out a better way to do this.
    _.each($scope.answers, function(element, key) {
      var setting = _.find($scope.settings, function(item) {
        if (item.id == key)
          return item;
        return null;
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
      });
    } else {
      $scope.loginPrompt(); //TODO: implement a callback
    }
  };

  $scope.simulate = function() {
    $scope.submit('simulate');
  };

  $scope.preview = function() {
    $scope.submit('+preview');
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
    console.log("Starting load")
    this.klass = $resource('/:tenantId/deployments/:id.json');
    this.klass.get($routeParams, function(data, getResponseHeaders){
      console.log("Load returned");
      $scope.data = data
      $scope.data_json = JSON.stringify(data, null, 2);
      console.log("Done loading")
    });
  }
  
  $scope.save = function() {
    var editor = _.find($('.CodeMirror'), function(c) {
      return c.CodeMirror.getTextArea().id == 'source';
      });

    if ($scope.auth.loggedIn) {
      var klass = $resource('/:tenantId/deployments/:id/.json', null, {'get': {method:'GET'}, 'save': {method:'PUT'}});
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
    console.log("Starting load")
    this.klass = $resource('/:tenantId/providers/.json');
    this.klass.get({tenantId: $scope.auth.tenantId}, function(list, getResponseHeaders){
      console.log("Load returned");
      items.receive(list, function(item, key) {
        return {id: key, name: item.name, vendor: item.vendor}});
      $scope.count = items.count;
      $scope.items = items.all;
      console.log("Done loading")
    });
  }

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
    console.log("Starting load")
    this.klass = $resource('/:tenantId/environments/.json');
    this.klass.get({tenantId: $scope.auth.tenantId}, function(list, getResponseHeaders){
      console.log("Load returned");
      items.receive(list, function(item, key) {
        return {id: key, name: item.name, vendor: item.vendor, providers: item.providers}});
      $scope.count = items.count;
      $scope.items = items.all;
      console.log("Done loading")
    });
  }

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
            default_vendor = '[missing vendor]'
        _.each(providers, function(provider, key, provider) {
            if (key == 'common')
                return;
            name = provider.vendor || default_vendor;
            name += '.' + key;
            list.push(name);
        });
    }
    return list.join(", ");
  }
}


// Other stuff
document.addEventListener('DOMContentLoaded', function(e) {
  //On mobile devices, hide the address bar
  window.scrollTo(0, 0);
}, false);

//Initial Wordpress Templates
WPBP = {
    "DBaaS":{
        "id":"d8fcfc17-b515-473a-9fe1-6d4e3356ef8d",
        "description":"Create a multi-server WordPress deployment on any cloud account using the Chef cookbooks created by the Managed Cloud team.",
        "services":{
            "lb":{
                "open-ports":[
                    "80/tcp"
                ],
                "component":{
                    "interface":"proxy",
                    "type":"load-balancer",
                    "constraints":[
                        {
                            "algorithm":"ROUND_ROBIN"
                        }
                    ]
                },
                "relations":{
                    "web":"http",
                    "master":"http"
                },
                "exposed":true
            },
            "master":{
                "component":{
                    "type":"application",
                    "name":"wordpress-master-role",
                    "constraints":[
                        {
                            "wordpress/version":"3.4.1"
                        }
                    ]
                },
                "relations":{
                    "wordpress/database":{
                        "interface":"mysql",
                        "service":"backend"
                    },
                    "varnish/master_backend":{
                        "interface":"host",
                        "attribute":"private_ip"
                    },
                    "lsyncd/slaves":{
                        "interface":"host",
                        "service":"web",
                        "attribute":"private_ip"
                    },
                    "mysql":{
                        "interface":"mysql",
                        "service":"backend"
                    }
                },
                "constraints":[
                    {
                        "count":1
                    }
                ]
            },
            "web":{
                "component":{
                    "type":"application",
                    "name":"wordpress-web-role",
                    "constraints":[
                        {
                            "wordpress/version":"3.4.1"
                        }
                    ]
                },
                "relations":{
                    "varnish/master_backend":{
                        "interface":"host",
                        "service":"master",
                        "attribute":"private_ip"
                    },
                    "lsyncd/slaves":{
                        "interface":"host",
                        "attribute":"private_ip"
                    },
                    "wordpress/database":{
                        "interface":"mysql",
                        "service":"backend"
                    },
                    "mysql":{
                        "interface":"mysql",
                        "service":"backend"
                    }
                }
            },
            "backend":{
                "component":{
                    "interface":"mysql",
                    "type":"database"
                }
            }
        },
        "options":{
            "domain":{
                "regex":"^(([a-zA-Z]|[a-zA-Z][a-zA-Z0-9\\-]*[a-zA-Z0-9])\\.)*([A-Za-z]|[A-Za-z][A-Za-z0-9\\-]*[A-Za-z0-9])$",
                "constrains":[
                    {
                        "setting":"apache/domain_name",
                        "service":"web",
                        "resource_type":"application"
                    },
                    {
                        "setting":"apache/domain_name",
                        "service":"master",
                        "resource_type":"application"
                    }
                ],
                "description":"The domain you wish to host your blog on. (ex: example.com)",
                "label":"Domain",
                "sample":"example.com",
                "type":"combo",
                "required":true,
                "choice":[
                    
                ]
            },
            "path":{
                "constrains":[
                    {
                        "setting":"wordpress/path",
                        "service":"web",
                        "resource_type":"application"
                    },
                    {
                        "setting":"wordpress/path",
                        "service":"master",
                        "resource_type":"application"
                    }
                ],
                "description":"The path you wish to host your blog on under your domain. (ex: /blog)",
                "default":"/",
                "label":"Path",
                "sample":"/blog",
                "type":"string"
            },
            "register-dns":{
                "default":false,
                "type":"boolean",
                "label":"Create DNS records",
                "constrains":[
                    {
                    	"setting":"create_dns",
                    	"service":"lb",
                    	"resource_type":"load-balancer"
                    }
                ]
            },
            "region":{
                "required":true,
                "type":"select",
                "default":"ORD",
                "label":"Region",
                "choice":[
                    "DFW",
                    "ORD",
                    "LON"
                ]
            },
            "prefix":{
                "constrains":[
                    {
                        "setting":"wordpress/database/prefix",
                        "service":"master",
                        "resource_type":"application"

                    },
                    {
                        "setting":"wordpress/database/prefix",
                        "service":"web",
                        "resource_type":"application"

                    }
                ],
                "help":"Note that this also the user name, database name, and also identifies this\nwordpress install from other ones you might add later to the same deployment.\n",
                "default":"wp_",
                "required":true,
                "label":"Prefix",
                "type":"string",
                "description":"The application ID (and wordpress table prefix)."
            },
            "username":{
                "type":"string",
                "description":"Username to use for service.",
                "label":"Username",
                "constrains":[
                	{
                    	"setting":"name",
                    	"resource_type":"wp user"
                	}
                ]
            },
            "password":{
                "type":"password",
                "description":"Password to use for database and system user. Click the generate button to generate a random password.",
                "label":"Password",
                "constrains":[
                    {
                        "setting":"password",
                        "resource_type":"wp user"
                    }
                ]
            },
            "os":{
                "constrains":[
                    {
                        "setting":"os",
                        "service":"web",
                        "resource_type":"compute"
                    },
                    {
                        "setting":"os",
                        "service":"master",
                        "resource_type":"compute"
                    }
                ],
                "description":"The operating system for the web servers.",
                "default":"Ubuntu 12.04",
                "label":"Operating System",
                "type":"select",
                "choice":[
                    //"Ubuntu 11.10",
                    "Ubuntu 12.04",
                    //"CentOS",
                    //"RHEL 6"
                ]
            },
            "web_server_size":{
                "constrains":[
                    {
                        "setting":"memory",
                        "service":"web",
                        "resource_type":"compute"
                    },
                    {
                        "setting":"memory",
                        "service":"master",
                        "resource_type":"compute"
                    }
                ],
                "description":"The size of the instance in MB of RAM.",
                "default":1024,
                "label":"Web Server Size",
                "type":"select",
                "choice":[
                    {
                        "name":"512 Mb",
                        "value":512
                    },
                    {
                        "name":"1 Gb",
                        "value":1024
                    },
                    {
                        "name":"2 Gb",
                        "value":2048
                    },
                    {
                        "name":"4 Gb",
                        "value":4096
                    },
                    {
                        "name":"8 Gb",
                        "value":8092
                    },
                    {
                        "name":"16 Gb",
                        "value":16384
                    },
                    {
                        "name":"30 Gb",
                        "value":30720
                    }
                ]
            },
            "web_server_count":{
                "constrains":[
                    {
                        "setting":"count",
                        "service":"web",
                        "resource_type":"application"
                    }
                ],
                "description":"The number of WordPress servers in addition to the master server.",
                "default":1,
                "label":"Additional Web Servers",
                "type":"int",
                "constraints":[
                    {
                        "greater-than":0
                    }
                ]
            },
            "database_memory":{
                "constrains":[
                    {
                        "setting":"memory",
                        "service":"backend",
                        "resource_type":"compute"
                    }
                ],
                "description":"The size of the database instance in MB of RAM.",
                "default":512,
                "label":"Database Size",
                "type":"select",
                "choice":[
                    {
                        "name":"512 Mb",
                        "value":512
                    },
                    {
                        "name":"1024 Mb",
                        "value":1024
                    },
                    {
                        "name":"2048 Mb",
                        "value":2048
                    },
                    {
                        "name":"4096 Mb",
                        "value":4096
                    }
                ]
            },
            "database_volume_size":{
                "default":1,
                "constrains":[
                    {
                        "setting":"disk",
                        "service":"backend",
                        "resource_type":"database"
                    }
                ],
                "type":"int",
                "description":"The hard drive space available for the database instance in GB.",
                "label":"Database Disk Size",
                "constraints":[
                    {
                        "greater-than":0,
                        "less-than":51
                    }
                ]
            },
            "web_server_protocol":{
                "default":'http',
                "label":"HTTP Protocol",
                "type":"select",
                "choice":[
                    {
                        "name":"HTTP Only",
                        "value":"http",
                        "precludes":[
                            "ssl_certificate",
                            "ssl_private_key"
                        ]
                    },
                    {
                        "name":"HTTPS Only",
                        "value":"https",
                        "requires":[
                            "ssl_certificate",
                            "ssl_private_key"
                        ]
                    },
                    {
                        "name":"HTTP and HTTPS",
                        "value":"http_and_https",
                        "requires":[
                            "ssl_certificate",
                            "ssl_private_key"
                        ]
                    }
                ],
                "help":"Use HTTP, HTTPS (SSL), or both for web traffic. HTTPS requires an SSL certificate and private key.",
                "description":"Use HTTP, HTTPS (SSL), or both for web traffic. HTTPS requires an SSL certificate and private key.",
                "constrains":[
                    {
                        "setting":"protocol",
                        "service":"lb",
                        "resource_type":"load-balancer"
                    }
                ]
            },
            "ssl_certificate":{
                "sample":"-----BEGIN CERTIFICATE-----\nEncoded Certificate\n-----END CERTIFICATE-----\n",
                "constrains":[
                    {
                        "setting":"apache/ssl_cert",
                        "service":"web",
                        "resource_type":"application"
                    },
                    {
                        "setting":"apache/ssl_cert",
                        "service":"master",
                        "resource_type":"application"
                    }
                ],
                "type":"text",
                "description":"SSL certificate in PEM format. Make sure to include the BEGIN and END certificate lines.",
                "label":"SSL Certificate"
            },
            "ssl_private_key":{
                "sample":"-----BEGIN PRIVATE KEY-----\nEncoded key\n-----END PRIVATE KEY-----\n",
                "constrains":[
                    {
                        "setting":"apache/ssl_private_key",
                        "service":"web",
                        "resource_type":"application"
                    },
                    {
                        "setting":"apache/ssl_private_key",
                        "service":"master",
                        "resource_type":"application"
                    }
                ],
                "type":"text",
                "label":"SSL Certificate Private Key"
            }
        },
        "resources":{
            "wp keys":{
                "type":"key-pair",
                "constrains":[
                    {
                        "setting":"lsyncd/user/ssh_private_key",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"private_key"
                    },
                    {
                        "setting":"lsyncd/user/ssh_private_key",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"private_key"
                    },
                    {
                        "setting":"lsyncd/user/ssh_pub_key",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"public_key_ssh"
                    },
                    {
                        "setting":"lsyncd/user/ssh_pub_key",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"public_key_ssh"
                    }
                ]
            },
            "wp user":{
                "type":"user",
                "constrains":[
                    {
                        "setting":"lsyncd/user/name",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"lsyncd/user/name",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"mysql/database_name",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"mysql/database_name",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"wordpress/database/database_name",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"wordpress/database/database_name",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"database/name",
                        "service":"backend",
                        "resource_type":"database",
                        "attribute":"name"
                    },
                    {
                        "setting":"database/username",
                        "service":"backend",
                        "resource_type":"database",
                        "attribute":"name"
                    },
                    {
                        "setting":"database/password",
                        "service":"backend",
                        "resource_type":"database",
                        "attribute":"password"
                    },
                    {
                        "setting":"mysql/password",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"password"
                    },
                    {
                        "setting":"mysql/password",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"password"
                    },
                    {
                        "setting":"mysql/username",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"mysql/username",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"wordpress/database/password",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"password"
                    },
                    {
                        "setting":"wordpress/database/password",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"password"
                    },
                    {
                        "setting":"wordpress/database/username",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"wordpress/database/username",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"wordpress/user/name",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"wordpress/user/name",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"wordpress/user/password",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"password"
                    },
                    {
                        "setting":"wordpress/user/password",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"password"
                    },
                    {
                        "setting":"wordpress/user/hash",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"hash"
                    },
                    {
                        "setting":"wordpress/user/hash",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"hash"
                    }
                ]
            }
        },
        "name":"Managed Cloud WordPress w/ Cloud Databases"
    },
    "MySQL":{
        "id":"0255a076c7cf4fd38c69b6727f0b37ea",
        "description":"Create a multi-server WordPress deployment on any cloud account using the Chef cookbooks created by the Managed Cloud team.",
        "services":{
            "lb":{
                "open-ports":[
                    "80/tcp"
                ],
                "component":{
                    "interface":"proxy",
                    "type":"load-balancer",
                    "constraints":[
                        {
                            "algorithm":"ROUND_ROBIN"
                        }
                    ]
                },
                "relations":{
                    "web":"http",
                    "master":"http"
                },
                "exposed":true
            },
            "master":{
                "component":{
                    "type":"application",
                    "name":"wordpress-master-role",
                    "constraints":{
                        "wordpress/version":"3.4.1",
                        "wordpress/database/create_db":"true",
                        "wordpress/database/create_db_user":"true"
                    }
                },
                "relations":{
                    "wordpress/database":{
                        "interface":"mysql",
                        "service":"backend"
                    },
                    "wordpress/database/host":{
                        "interface":"host",
                        "service":"backend",
                        "attribute":"private_ip"
                    },
                    "wordpress/database/server_root_password":{
                        "interface":"host",
                        "service":"backend",
                        "attribute":"password"
                    },
                    "varnish/master_backend":{
                        "interface":"host",
                        "attribute":"private_ip"
                    },
                    "lsyncd/slaves":{
                        "interface":"host",
                        "service":"web",
                        "attribute":"private_ip"
                    }
                },
                "constraints":[
                    {
                        "count":1
                    }
                ]
            },
            "web":{
                "component":{
                    "type":"application",
                    "name":"wordpress-web-role",
                    "constraints":{
                            "wordpress/version":"3.4.1"
                        }
                },
                "relations":{
                    "varnish/master_backend":{
                        "interface":"host",
                        "service":"master",
                        "attribute":"private_ip"
                    },
                    "lsyncd/slaves":{
                        "interface":"host",
                        "attribute":"private_ip"
                    },
                    "wordpress/database/host":{
                        "interface":"host",
                        "service":"backend",
                        "attribute":"private_ip"
                    }
                }
            },
            "backend":{
                "component":{
                    "name":"mysql-master-role",
                    "interface":"mysql",
                    "type":"database"
                },
                "relations":{
                    "mysql/host":{
                        "interface":"host",
                        "attribute":"private_ip"
                    },
                    "mysql/server_root_password":{
                        "interface":"host",
                        "attribute":"password"
                    }
                }
            }
        },
        "options":{
            "domain":{
                "regex":"^(([a-zA-Z]|[a-zA-Z][a-zA-Z0-9\\-]*[a-zA-Z0-9])\\.)*([A-Za-z]|[A-Za-z][A-Za-z0-9\\-]*[A-Za-z0-9])$",
                "constrains":[
                    {
                        "setting":"apache/domain_name",
                        "service":"web",
                        "resource_type":"application"
                    },
                    {
                        "setting":"apache/domain_name",
                        "service":"master",
                        "resource_type":"application"
                    }
                ],
                "description":"The domain you wish to host your blog on. (ex: example.com)",
                "label":"Domain",
                "sample":"example.com",
                "type":"combo",
                "required":true,
                "choice":[
                    
                ]
            },
            "path":{
                "constrains":[
                    {
                        "setting":"wordpress/path",
                        "service":"web",
                        "resource_type":"application"
                    },
                    {
                        "setting":"wordpress/path",
                        "service":"master",
                        "resource_type":"application"
                    }
                ],
                "description":"The path you wish to host your blog on under your domain. (ex: /blog)",
                "default":"/",
                "label":"Path",
                "sample":"/blog",
                "type":"string"
            },
            "register-dns":{
                "default":false,
                "type":"boolean",
                "label":"Create DNS records"
            },
            "region":{
                "required":true,
                "type":"select",
                "default":"ORD",
                "label":"Region",
                "choice":[
                    "DFW",
                    "ORD",
                    "LON"
                ]
            },
            "prefix":{
                "constrains":[
                    {
                        "setting":"wordpress/database/prefix",
                        "service":"master",
                        "resource_type":"application"
                    },
                    {
                        "setting":"wordpress/database/prefix",
                        "service":"web",
                        "resource_type":"application"
                    }
                ],
                "help":"Note that this also the user name, database name, and also identifies this\nwordpress install from other ones you might add later to the same deployment.\n",
                "default":"wp_",
                "required":true,
                "label":"Prefix",
                "type":"string",
                "description":"The application ID (and wordpress table prefix)."
            },
            "password":{
                "type":"password",
                "description":"Password to use for service. Click the generate button to generate a random password.",
                "label":"Password",
                "constrains":[
                    {
                        "setting":"password",
                        "resource_type":"wp user"
                    }
                ]
            },
            "username":{
                "type":"string",
                "description":"Username to use for service.",
				"required":true,
                "label":"Username",
                "constrains":[
                	{
                    	"setting":"name",
                    	"resource_type":"wp user"
                	}
                ]
            },
            "os":{
                "constrains":[
                    {
                        "setting":"os",
                        "service":"web",
                        "resource_type":"compute"
                    },
                    {
                        "setting":"os",
                        "service":"master",
                        "resource_type":"compute"
                    },
                    {
                        "setting":"os",
                        "service":"backend",
                        "resource_type":"compute"
                    }
                ],
                "description":"The operating system for the all servers.",
                "default":"Ubuntu 12.04",
                "label":"Operating System",
                "type":"select",
                "choice":[
                    //"Ubuntu 11.10",
                    "Ubuntu 12.04",
                    //"CentOS",
                    //"RHEL 6"
                ]
            },
            "server_size":{
                "constrains":[
                    {
                        "setting":"memory",
                        "service":"web",
                        "resource_type":"compute"
                    },
                    {
                        "setting":"memory",
                        "service":"master",
                        "resource_type":"compute"
                    }
                ],
                "description":"The size of the Wordpress server instances in MB of RAM.",
                "default":512,
                "label":"Server Size",
                "type":"select",
                "choice":[
                    {
                        "name":"512 Mb",
                        "value":512
                    },
                    {
                        "name":"1 Gb",
                        "value":1024
                    },
                    {
                        "name":"2 Gb",
                        "value":2048
                    },
                    {
                        "name":"4 Gb",
                        "value":4096
                    },
                    {
                        "name":"8 Gb",
                        "value":8092
                    },
                    {
                        "name":"16 Gb",
                        "value":16384
                    },
                    {
                        "name":"30 Gb",
                        "value":30720
                    }
                ]
            },
            "web_server_count":{
                "constrains":[
                    {
                        "setting":"count",
                        "service":"web",
                        "resource_type":"application"
                    }
                ],
                "description":"The number of WordPress servers in addition to the master server",
                "default":1,
                "label":"Additional Web Servers",
                "type":"int",
                "constraints":[
                    {
                        "greater-than":0
                    }
                ]
            },
            "database_size":{
                "constrains":[
                    {
                        "setting":"memory",
                        "service":"backend",
                        "resource_type":"compute"
                    }
                ],
                "description":"The size of the database instance in MB of RAM.",
                "default":1024,
                "label":"Database Instance Size",
                "type":"select",
                "choice":[
                    {
                        "name":"512 Mb (20 Gb disk)",
                        "value":512
                    },
                    {
                        "name":"1 Gb (40 Gb disk)",
                        "value":1024
                    },
                    {
                        "name":"2 Gb (80 Gb disk)",
                        "value":2048
                    },
                    {
                        "name":"4 Gb (160 Gb disk)",
                        "value":4096
                    },
                    {
                        "name":"8 Gb (320 Gb disk)",
                        "value":8192
                    },
                    {
                        "name":"16 Gb (620 Gb disk)",
                        "value":15872
                    },
                    {
                        "name":"30 Gb (1.2 Tb disk)",
                        "value":30720
                    }
                ]
            },
            "web_server_protocol":{
                "default":'http',
                "label":"HTTP Protocol",
                "type":"select",
                "choice":[
                    {
                        "name":"HTTP Only",
                        "value":"http",
                        "precludes":[
                            "ssl_certificate",
                            "ssl_private_key"
                        ]
                    },
                    {
                        "name":"HTTPS Only",
                        "value":"https",
                        "requires":[
                            "ssl_certificate",
                            "ssl_private_key"
                        ]
                    },
                    {
                        "name":"HTTP and HTTPS",
                        "value":"http_and_https",
                        "requires":[
                            "ssl_certificate",
                            "ssl_private_key"
                        ]
                    }
                ],
                "help":"Use HTTP, HTTPS (SSL), or both for web traffic. HTTPS requires an SSL certificate and private key.",
                "description":"Use HTTP, HTTPS (SSL), or both for web traffic. HTTPS requires an SSL certificate and private key.",
                "constrains":[
                    {
                        "setting":"protocol",
                        "service":"lb",
                        "resource_type":"load-balancer"
                    }
                ]
            },
            "ssl_certificate":{
                "sample":"-----BEGIN CERTIFICATE-----\nEncoded Certificate\n-----END CERTIFICATE-----\n",
                "constrains":[
                    {
                        "setting":"apache/ssl_cert",
                        "service":"web",
                        "resource_type":"application"
                    },
                    {
                        "setting":"apache/ssl_cert",
                        "service":"master",
                        "resource_type":"application"
                    }
                ],
                "type":"text",
                "description":"SSL certificate in PEM format. Make sure to include the BEGIN and END certificate lines.",
                "label":"SSL Certificate"
            },
            "ssl_private_key":{
                "sample":"-----BEGIN PRIVATE KEY-----\nEncoded key\n-----END PRIVATE KEY-----\n",
                "constrains":[
                    {
                        "setting":"apache/ssl_private_key",
                        "service":"web",
                        "resource_type":"application"
                    },
                    {
                        "setting":"apache/ssl_private_key",
                        "service":"master",
                        "resource_type":"application"
                    }
                ],
                "type":"text",
                "label":"SSL Certificate Private Key"
            }
        },
        "resources":{
            "wp keys":{
                "type":"key-pair",
                "constrains":[
                    {
                        "setting":"lsyncd/user/ssh_private_key",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"private_key"
                    },
                    {
                        "setting":"lsyncd/user/ssh_private_key",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"private_key"
                    },
                    {
                        "setting":"lsyncd/user/ssh_pub_key",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"public_key_ssh"
                    },
                    {
                        "setting":"lsyncd/user/ssh_pub_key",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"public_key_ssh"
                    }
                ]
            },
            "wp user":{
                "type":"user",
                "constrains":[
                    {
                        "setting":"lsyncd/user/name",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"lsyncd/user/name",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"mysql/database_name",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"mysql/database_name",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"wordpress/database/database_name",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"wordpress/database/database_name",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"mysql/password",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"password"
                    },
                    {
                        "setting":"mysql/password",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"password"
                    },
                    {
                        "setting":"mysql/username",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"mysql/username",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"wordpress/database/password",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"password"
                    },
                    {
                        "setting":"wordpress/database/password",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"password"
                    },
                    {
                        "setting":"wordpress/database/username",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"wordpress/database/username",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"wordpress/user/name",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"wordpress/user/name",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"name"
                    },
                    {
                        "setting":"wordpress/user/password",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"password"
                    },
                    {
                        "setting":"wordpress/user/password",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"password"
                    },
                    {
                        "setting":"wordpress/user/hash",
                        "service":"web",
                        "resource_type":"application",
                        "attribute":"hash"
                    },
                    {
                        "setting":"wordpress/user/hash",
                        "service":"master",
                        "resource_type":"application",
                        "attribute":"hash"
                    }
                ]
            }
        },
        "name":"Managed Cloud WordPress (MySQLonVMs)"
    }
};

//Default Environments
ENVIRONMENTS = {
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

