'use strict';

/**
 *   environments
 */

function EnvironmentListCtrl($scope, $location, $http) {

  // Get the environments
  cm.Resource.query($http, $scope, 'environments').success(function(data, status) {
    $scope.environments = data;
  });

  $scope.provider_count = function(environment) {
    if (environment.providers === null) {
      return 0;
    } else {
      return Object.keys(environment.providers).length;
    }
  };

  $scope.delete = function(environment) {
    environment.$delete();
  };

  $scope.create = function() {
    $location.path('/environments/new');
  };

  $scope.navigate = function(environmentId) {
    $location.path('/environments/' + environmentId);
  };
}
EnvironmentListCtrl.$inject = ['$scope', '$location', '$http'];

/**
 *   environments/:environmentId
 */

function EnvironmentDetailCtrl($scope, $location, $http, $routeParams) {
  $scope.providers = {};
  $scope.selectedProviders = {};
  $scope.apiProviders = null;

  if ($routeParams.environmentId != "new") {
    cm.Resource.get($http, $scope, 'environments', $routeParams.environmentId).success(function(data, status) {
      $scope.environment = data;
    });
  } else {
    $scope.environment = {};
  }

  cm.Resource.query($http, $scope, 'providers')
    .success(function(data) {
      $scope.apiProviders = data;

      _.each(data, function(provider) {
        _.each(provider.provides, function(provides) {
          var name = _.first(_.keys(provides));
          if (name !== null) {
            if ($scope.providers[name] === null) {
              $scope.providers[name] = {label:name, options: []};
              $scope.selectedProviders[name] = this.vendor + '.' + this.name;
            }

            var listElement = {
              label: this.name + ' (' + provides[name] + ')',
              value: this.vendor + '.' + this.name
            };
            $scope.providers[name].options.push(listElement);
          }
        }, provider);
      });
    });



  $scope.update = function(environment) {
    $scope.environment = angular.copy(environment);

    //build the providers
    var newProviders = {};
    _.each($scope.selectedProviders, function(provider, key) {
      var n = provider.split('.')[1];   // TODO: This feels like an ugly hack.        
      newProviders[n] = $scope.apiProviders[provider];
    });

    $scope.environment["providers"] = newProviders;

    cm.Resource.saveOrUpdate($http, $scope, 'environments', $scope.environment).success(function(data, status) {
      $location.path('/environments');
    });
  };

  $scope.reset = function() {
    $scope.environment = Environment.get({
      environmentId: $routeParams.environmentId
    });
  };
}
EnvironmentDetailCtrl.$inject = ['$scope', '$location', '$http', '$routeParams'];

/**
 *   blueprints
 */

function BlueprintListCtrl($scope, $location, $http) {
  //$scope.blueprints = Blueprint.query();
  cm.Resource.query($http, $scope, 'blueprints').success(function(data, status) {
    $scope.blueprints = data;
  });

  $scope.serviceList = function(blueprint) {
    return blueprint.services ? Object.keys(blueprint.services).join(', ') : 0;
  };

  $scope.detail = function(blueprintId) {
    $location.path('/blueprints/' + blueprintId);
  };

  $scope.newDeployment = function(blueprintId) {
    $location.path('/deployments/new').search({
      blueprintId: blueprintId
    });
  };

}
BlueprintListCtrl.$inject = ['$scope', '$location', '$http'];

/**
 *   blueprints
 */

function BlueprintDetailCtrl($scope, $location, $http, $routeParams) {
  cm.Resource.get($http, $scope, 'blueprints', $routeParams.blueprintId)
    .success(function(data) {
      $scope.blueprint = data;
      $scope.stringify = JSON.stringify($scope.blueprint, null, '\t');
      $scope.codeMirror = CodeMirror.fromTextArea($('#editor').get(0), {
        value: $scope.stringify,
        mode: 'javascript',
        lineNumbers: true
      });
    });

  $scope.update = function(blueprint) {
    $scope.blueprint = angular.copy(JSON.parse(scope.stringify));

    if ($scope.blueprint.id === null) {
      $scope.blueprint.$save();
    } else {
      $scope.blueprint.$update();
    }

    $location.path('/blueprints');
  };

  $scope.reset = function() {
    $scope.blueprint = Blueprint.get({
      blueprintId: $routeParams.blueprintId
    });
  };
}
BlueprintDetailCtrl.$inject = ['$scope', '$location', '$http', '$routeParams'];

/**
 *   Authentication
 */

function AuthCtrl($scope, $location, $cookieStore) {
  $scope.location = 'us';

  $scope.auth = {
    username: '',
    key: '',
    password: ''
  };
  $scope.signedIn = false;

  var catalog = $cookieStore.get('auth');
  if (catalog) {
    cm.auth.setServiceCatalog(catalog);
    $scope.auth.username = cm.auth.getUsername();
  }

  // Call any time to ensure client is authentication
  $scope.signIn = function() {
    if (!cm.auth.isAuthenticated()) {
      var modal = $('#auth_modal');
      modal.modal({
        keyboard: false,
        show: true
      });

      modal.modal('show');
    }
    return $scope.authenticated();
  };

  $scope.authenticated = function() {
    var latest = cm.auth.isAuthenticated();
    if ($scope.signedIn != latest)
      $scope.signedIn = latest;
    return latest;
  };

  $scope.signOut = function() {
    $scope.auth.username = '';
    $scope.auth.key = '';
    $scope.auth.password = '';
    $scope.auth.catalog = null;
    $cookieStore.put('auth', null);
    $cookieStore.remove('auth');
    cm.auth.setServiceCatalog(null);
    $location.path('/');
    $scope.signedIn = false;
    //$('#auth_modal').modal('show');
  };

  $scope.authenticate = function() {
    var location = "https://identity.api.rackspacecloud.com/v2.0/tokens";
    if ($scope.location == 'uk') {
      location = "https://lon.identity.api.rackspacecloud.com/v2.0/tokens";
    }

    var data;
    if ($scope.auth.key) {
       data = JSON.stringify({
        "auth": {
          "RAX-KSKEY:apiKeyCredentials": {
            "username": $scope.auth.username,
            "apiKey": $scope.auth.key
          }
        }
      });
     } else if ($scope.auth.password) {
       data = JSON.stringify({
          "auth": {
            "passwordCredentials": {
              "username": $scope.auth.username,
              "password": $scope.auth.password
            }
          }
        });
     }

    return $.ajax({
      type: "POST",
      contentType: "application/json; charset=utf-8",
      headers: {
        "X-Auth-Source": location
      },
      dataType: "json",
      url: "/authproxy",
      data: data
    }).always(function(json) {
      cm.auth.setServiceCatalog(json);
      $cookieStore.put('auth', json);
    }).success(function() {
      $('#auth_modal').modal('hide');
      $scope.signedIn = true;
    }).error(function() {
      $("#auth_error_text").html("Something bad happened");
      $("#auth_error").show();
    });
  };
}
AuthCtrl.$inject = ['$scope', '$location', '$cookieStore'];

/**
 *   Profile
 */

function ProfileCtrl($scope, $location) {

}
ProfileCtrl.$inject = ['$scope', '$location'];

/**
 *   Deployments
 */

function DeploymentListCtrl($scope, $location, $http) {
  cm.Resource.query($http, $scope, 'deployments').success(function(data, status) {
    $scope.deployments = data;
  });

  $scope.delete = function(deployment) {
    cm.Resource.del($http, $scope, 'deployments', deployment).success(function(data, status) {
      $location.path('/deployments');
    });
  };

  $scope.create = function() {
    $location.path('/deployments/new');
  };

  $scope.navigate = function(deploymentId) {
    $location.path('/deployments/' + deploymentId);
  };

}
DeploymentListCtrl.$inject = ['$scope', '$location', '$http'];


/**
 *  Deployment status
 */

function DeploymentStatusCtrl($scope, $location, $http, $routeParams) {
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

  cm.Resource.get($http, $scope, 'deployments', $routeParams.deploymentId)
    .success(function(deployment) {
      $scope.deployment = deployment;
      $scope.refresh();
    });

  $scope.percentComplete = function() {
    console.log( (($scope.totalTime - $scope.timeRemaining) / $scope.totalTime) * 100 );
    return (($scope.totalTime - $scope.timeRemaining) / $scope.totalTime) * 100;
  };

  $scope.refresh = function() {
    cm.Resource.get($http, $scope, 'workflows', $scope.deployment.id)
      .success(function(workflow) {
        $scope.workflow = workflow;
        $scope.totalTime = 0;

        $scope.tasks = $scope.flattenTasks({}, workflow.task_tree);
        $scope.timeRemaining = $scope.totalTime;
        $scope.jit = $scope.jitTasks($scope.tasks);

        $scope.renderWorkflow($scope.jit);
        setTimeout($scope.refresh, 1000);
      });
  }

  $scope.renderWorkflow = function(tasks) {
    var template = $('#task').html();
    var container = $('#task_container').empty();

    for(var i = 0; i < Math.floor(tasks.length/4); i++) {
      var div = $('<div class="row">');
      var row = tasks.slice(i*4, (i+1)*4);
      _.each(row, function(task) {
        div.append(Mustache.render(template, task));        
      });

      container.append(div);
    }

    $('.task').hover(
      function() {
        //hover-in
        $(this).addClass('hovering');
        $scope.showConnections($(this));
      },
      function() {
        $(this).removeClass('hovering');
      }
    );
  };

  $scope.showConnections = function(task_div) {
    jsPlumb.Defaults.Container = "task_container";

    var selectedTask = _.find($scope.tasks, function(task) {
      if (task.id === parseInt(task_div.attr('id'))) {
        return task;
      }
    });

    //jsPlumb.addEndpoint(selectedTask.id);
    _.each(selectedTask.children, function(child) {
      //jsPlumb.addEndpoint(child.id);

      jsPlumb.connect({
        source: selectedTask.id,
        target: child.id
      });
    });
  };

  $scope.flattenTasks = function(accumulator, tree) {
    accumulator[tree.task_spec] = tree;

    if (tree.children.length > 0) {
      _.each(tree.children, function(child, index) {
        $scope.totalTime += parseInt(child["internal_attributes"]["estimated_completed_in"], 10);
        $.extend(accumulator, $scope.flattenTasks(accumulator, tree.children[index]));
      });
    }

    return accumulator;
  };

  $scope.jitTasks = function(tasks) {
    var jsonTasks = [];

    _.each(tasks, function(task) {
      var adjacencies = [];
      _.each(task.children, function(child) {
        var adj = {
          nodeTo: child.task_spec,
          nodeFrom: task.task_spec,
          data: {}
        };
        adjacencies.push(adj);
      });

      var t = {
        id: task.id,
        name: task.task_spec,
        adjacencies: adjacencies,
        state: $scope.colorize(task),
        data: {
          "$color": "#83548B",
          "$type": "circle"
        }
      };
      jsonTasks.push(t);
    });

    return jsonTasks;
  };

  /**
   *  FUTURE    =   1
   *  LIKELY    =   2
   *  MAYBE     =   4
   *  WAITING   =   8
   *  READY     =  16
   *  CANCELLED =  32
   *  COMPLETED =  64
   *  TRIGGERED = 128
   *
   *  TODO: This will be fixed in the API, see:
   *    https://github.rackspace.com/checkmate/checkmate/issues/45
   */
  $scope.iconify = function(state) {
    switch(state) {
      case 1:
        return "icon-fast-forward";
      case 2:
        return "icon-thumbs-up";
      case 4:
        return "icon-hand-right";
      case 8:
        return "icon-pause";
      case 16:
        return "icon-plus";
      case 32:
        return "icon-remove";
      case 64:
        return "icon-ok";
      case 128:
        return "icon-adjust";
      default:
        console.log("Invalid state '" + state + "'.");
        return "icon-question-sign";
    }
  };

  /**
   *  See above.
   *
   */
  $scope.colorize = function(task) {
    switch(task.state) {
      case 1:
        $scope.taskStates["future"] += 1;
        return "alert-waiting";        
      case 2:
        $scope.taskStates["likely"] += 1;
        return "alert-waiting";
      case 4:
        $scope.taskStates["maybe"] += 1;
        return "alert-waiting";
      case 8:
        $scope.taskStates["waiting"] += 1;
        return "alert-waiting";
      case 16:
        $scope.taskStates["ready"] += 1;
        return "alert-info";
      case 128:
        $scope.taskStates["triggered"] += 1;
        return "alert-info";
      case 32:
        $scope.taskStates["cancelled"] += 1;
        return "alert-error";
      case 64:
        $scope.taskStates["completed"] += 1;
        $scope.timeRemaining -= parseInt(task["internal_attributes"]["estimated_completed_in"], 10);
        return "alert-success";
      default:
        console.log("Invalid state '" + state + "'.");
        return "unkonwn";
    }
  };
}
DeploymentStatusCtrl.$inject = ['$scope', '$location', '$http', '$routeParams'];

/**
 *   New Deployment
 */
function DeploymentNewCtrl($scope, $location, $routeParams, $http) {
  var ctrl = new DeploymentInitCtrl($scope, $location, $routeParams, $http);
  return ctrl;
}
DeploymentNewCtrl.$inject = ['$scope', '$location', '$routeParams', '$http'];

function DeploymentTryCtrl($scope, $location, $routeParams, $http) {
  $scope.environments = [WPENV];
  $scope.blueprints = [WPBP];
  var ctrl = new DeploymentInitCtrl($scope, $location, $routeParams, $http, WPBP, WPENV);
  $scope.updateSettings();
  return ctrl;
}
DeploymentTryCtrl.$inject = ['$scope', '$location', '$routeParams', '$http'];

function DeploymentInitCtrl($scope, $location, $routeParams, $http, blueprint, environment) {
  $scope.environment = environment;
  $scope.blueprint = blueprint;
  $scope.answers = {};

  $scope.updateSettings = function() {
    $scope.settings = [];
    $scope.answers = {};

    if ($scope.blueprint) {
      $scope.settings = $scope.settings.concat(cm.Settings.getSettingsFromBlueprint($scope.blueprint));
    }

    if ($scope.environment) {
      $scope.settings = $scope.settings.concat(cm.Settings.getSettingsFromEnvironment($scope.environment));
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

      return template ? Mustache.render(template, setting) : "";
  };

  $scope.showSettings = function() {
    return !($scope.environment && $scope.blueprint);
  };

  $scope.submit = function(simulate) {
    var deployment = {};

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

    var resource = 'deployments';
    if (simulate) {
      resource = 'deployments/simulate';
    }

    cm.Resource.saveOrUpdate($http, $scope, resource, deployment)
      .success(function(data, status, headers) {
        var deploymentId = headers('location').split('/')[3];
        $location.path('deployments/' + deploymentId);
      })
      .error(function(data, status, headers, config) {
        console.log("Error " + status + " creating new deployment.");
        console.log(deployment);

        //TODO: Need to slice out the data we are interested in.
        $scope.error = data;
        $('#error_modal').modal('show');
      });
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
DeploymentInitCtrl.$inject = ['$scope', '$location', '$routeParams', '$http'];

function ProviderListCtrl($scope, $location, $http) {

  cm.Resource.query($http, $scope, 'providers')
    .success(function(data) {
      $scope.providers = data;
    });

}
ProviderListCtrl.$inject = ['$scope', '$location', '$http'];
