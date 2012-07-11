'use strict'

/**
 *   environments
 */

function EnvironmentListCtrl($scope, $location, $http) {

  // Get the environments
  cm.Resource.query($http, 'environments').success(function(data, status) {
    $scope.environments = data;
  });

  $scope.provider_count = function(environment) {
    if (environment.providers == null) {
      return 0;
    } else {
      return Object.keys(environment.providers).length
    }
  }

  $scope.delete = function(environment) {
    environment.$delete();
  }

  $scope.create = function() {
    $location.path('/environments/new');
  }

  $scope.navigate = function(environmentId) {
    $location.path('/environments/' + environmentId);
  }
}
EnvironmentListCtrl.$inject = ['$scope', '$location', '$http'];

/**
 *   environments/:environmentId
 */

function EnvironmentDetailCtrl($scope, $location, $http, $routeParams) {
  cm.Resource.query($http, 'providers')
    .success(function(data) {
      $scope.providers = data;
    });

  // Munge the providers so they have an id I can use.
  var p = new Array();
  $scope.selectedProviders = {}
  for (var i in PROVIDERS) {
    p.push($.extend({
      id: i,
      select: null
    }, PROVIDERS[i]));
    $scope.selectedProviders[i] = null;
  }
  $scope.providers = p;

  if ($routeParams.environmentId != "new") {
    cm.Resource.get($http, 'environments', $routeParams.environmentId).success(function(data, status) {
      $scope.environment = data;
    });
  } else {
    $scope.environment = {};
  }

  $scope.update = function(environment) {
    $scope.environment = angular.copy(environment);

    //build the providers    
    $scope.environment.providers = {};
    _.each($scope.selectedProviders, function(provider, key) {
      $scope.environment.providers[key] = provider;
    });

    cm.Resource.saveOrUpdate($http, 'environments', $scope.environment).success(function(data, status) {
      $location.path('/environments');
    });
  }

  $scope.reset = function() {
    $scope.environment = Environment.get({
      environmentId: $routeParams.environmentId
    });
  }
}
EnvironmentDetailCtrl.$inject = ['$scope', '$location', '$http', '$routeParams'];

/**
 *   blueprints
 */

function BlueprintListCtrl($scope, $location, $http) {
  //$scope.blueprints = Blueprint.query();
  cm.Resource.query($http, 'blueprints').success(function(data, status) {
    $scope.blueprints = data;
  });

  $scope.serviceList = function(blueprint) {
    return blueprint.services ? Object.keys(blueprint.services).join(', ') : 0;
  }

  $scope.detail = function(blueprintId) {
    $location.path('/blueprints/' + blueprintId);
  }

  $scope.newDeployment = function(blueprintId) {
    $location.path('/deployments/new').search({
      blueprintId: blueprintId
    });
  }

}
BlueprintListCtrl.$inject = ['$scope', '$location', '$http']

/**
 *   blueprints
 */

function BlueprintDetailCtrl($scope, $location, $http, $routeParams) {
  cm.Resource.get($http, 'blueprints', $routeParams.blueprintId)
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
    $scope.blueprint = angular.copy(JSON.parse(scope.stringify))

    if ($scope.blueprint.id == null) {
      $scope.blueprint.$save();
    } else {
      $scope.blueprint.$update();
    }

    $location.path('/blueprints');
  }

  $scope.reset = function() {
    $scope.blueprint = Blueprint.get({
      blueprintId: $routeParams.blueprintId
    });
  }
}
BlueprintDetailCtrl.$inject = ['$scope', '$location', '$http', '$routeParams']

/**
 *   Authentication
 */

function AuthCtrl($scope, $location) {
  $scope.location = 'us';

  $scope.auth = {
    username: '',
    key: ''
  };

  if ($location.host() == "localhost") {
    $scope.auth.username = "rackcloudtech";
    $scope.auth.key = "a1207b3b4eb8638d02cdb1c4f3f36644";
  }


  var modal = $('#auth_modal');
  modal.modal({
    keyboard: false,
    show: true
  });

  if (!cm.auth.isAuthenticated()) {
    modal.modal('show');
  }

  $scope.authenticated = function() {
    return cm.auth.isAuthenticated();
  }

  $scope.signOut = function() {
    $scope.auth.username = '';
    $scope.auth.key = '';
    $scope.auth.catalog = null;
    $location('/');
    $('#auth_modal').modal('show');
  }

  $scope.authenticate = function() {
    var location = "https://identity.api.rackspacecloud.com/v2.0/tokens";
    if ($scope.location == 'uk') {
      location = "https://lon.identity.api.rackspacecloud.com/v2.0/tokens";
    }

    var data = JSON.stringify({
      "auth": {
        "RAX-KSKEY:apiKeyCredentials": {
          "username": $scope.auth.username,
          "apiKey": $scope.auth.key
        }
      }
    });

    return $.ajax({
      type: "POST",
      contentType: "application/json; charset=utf-8",
      headers: {
        "X-Auth-Source": location
      },
      dataType: "json",
      url: "/authproxy",
      data: data,
    }).always(function(json) {
      cm.auth.setServiceCatalog(json);
    }).success(function() {
      $('#auth_modal').modal('hide');
    }).error(function() {
      $("#auth_error_text").html("Something bad happened");
      $("#auth_error").show();
    });
  }
}
AuthCtrl.$inject = ['$scope', '$location']

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
  cm.Resource.query($http, 'deployments').success(function(data, status) {
    $scope.deployments = data;
  });

  $scope.delete = function(deployment) {
    cm.Resource.del($http, 'deployments', deployment).success(function(data, status) {
      $location('/deployments');
    });
  }

  $scope.create = function() {
    $location.path('/deployments/new');
  }

  $scope.navigate = function(deploymentId) {
    $location.path('/deployments/' + deploymentId);
  }

}
DeploymentListCtrl.$inject = ['$scope', '$location', '$http'];


/**
 *  Deployment status
 */

function DeploymentStatusCtrl($scope, $location, $http, $routeParams) {
  cm.Resource.get($http, 'deployments', $routeParams.deploymentId)
    .success(function(deployment) {
      $scope.deployment = deployment;

      // TODO: Do some magic to get the workflow id
      cm.Resource.get($http, 'workflows', "60fc11ab0bb74023b67995e9938ecc7b")
        .success(function(workflow) {
          $scope.workflow = workflow;
          $scope.task_specs = workflow.wf_spec.task_specs;

          $scope.tasks = $scope.flattenTasks({}, workflow.task_tree);
          $scope.jit = $scope.jitTasks($scope.tasks);
          cm.graph.createGraph("graph", $scope.jit);
        });
    });

  $scope.flattenTasks = function(accumulator, tree) {
    accumulator[tree.task_spec] = tree;

    if (tree.children.length > 0) {
      _.each(tree.children, function(child, index) {
        $.extend(accumulator, $scope.flattenTasks(accumulator, tree.children[index]));
      });
    }

    return accumulator;
  }

  $scope.jitTasks = function(tasks) {
    var jsonTasks = new Array();

    _.each(tasks, function(task) {
      var adjacencies = new Array();
      _.each(task.children, function(child) {
        var adj = {
          nodeTo: child.task_spec,
          nodeFrom: task.task_spec,
          data: {}        
        }
        adjacencies.push(adj);
      }); 

      var t = {
        id: task.task_spec,
        name: task.task_spec,
        adjacencies: adjacencies,
        data: {
          "$color": "#83548B",
          "$type": "circle"
        }
      }
      jsonTasks.push(t);
    });

    return jsonTasks;
  }

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
        break;
      case 2:
        return "icon-thumbs-up"
        break;
      case 4:
        return "icon-hand-right";
        break;
      case 8:
        return "icon-pause"
        break;
      case 16:
        return "icon-plus";
        break;
      case 32:
        return "icon-remove";
        break;
      case 64:
        return "icon-ok";
        break;
      case 128:
        return "icon-adjust";
        break;
      default:
        console.log("Invalid state '" + state + "'.");
        return "icon-question-sign"
      break;
    }
  }
}
DeploymentStatusCtrl.$inject = ['$scope', '$location', '$http', '$routeParams'];

/**
 *   Deployments
 */

function DeploymentNewCtrl($scope, $location, $routeParams, $http) {
  $scope.environment = null;
  $scope.blueprint = null;
  $scope.answers = {};

  $scope.updateSettings = function() {
    $scope.settings = new Array();
    $scope.answers = {};

    if ($scope.blueprint) {
      $scope.settings = $scope.settings.concat(cm.Settings.getSettingsFromBlueprint($scope.blueprint));
    }

    if ($scope.environment) {
      $scope.settings = $scope.settings.concat(cm.Settings.getSettingsFromEnvironment($scope.environment));
    }

    _.each($scope.settings, function(element, index) {
      if (element && element.id) {
        $scope.answers[element.id] = null;
      }
    });
  }

  $scope.renderSetting = function(setting) {
    if (!setting) {
      var message = "The requested setting is null";
      console.log(message);
      return "<em>" + message + "</em>";
    }

    if (!setting.type || !_.isString(setting.type)) {
      var message = "The requested setting '" + setting.id + "' has no type or the type is not a string."
      console.log(message);
      return "<em>" + message + "</em>";
    } else {
      var lowerType = setting.type.toLowerCase().trim();
    }

    var template = $('#setting-' + lowerType).html();

    if (template == null) {
      var message = "No template for setting type '" + setting.type + "'."
      console.log(message);
      return "<em>" + message + "</em>";
    }

    console.log(JSON.stringify(setting));

    return template ? Mustache.render(template, setting) : "";
  }

  $scope.submit = function() {
    var deployment = {};

    deployment.blueprint = $scope.blueprint;
    deployment.environment = $scope.environment;
    deployment.inputs = {};
    deployment.inputs.blueprint = $scope.answers;

    cm.Resource.saveOrUpdate($http, 'deployments', deployment)
      .success(function(data, status) {
        $location('/deployment/' + data.id);
      })
      .error(function(data,status) {
        console.log("Error " + status + " creating new deployment.");
        console.log(deployment);
      });
  }

  // Load blueprints
  cm.Resource.query($http, 'blueprints').success(function(data) {
    $scope.blueprints = data;

    if ($routeParams.blueprintId) {
      $scope.blueprint = _.find($scope.blueprints, function(bp) {
        return bp.id == $routeParams.blueprintId
      });
      $scope.updateSettings();
    }
  });

  // Load the environments
  cm.Resource.query($http, 'environments').success(function(data) {
    $scope.environments = data;
  });
}
DeploymentNewCtrl.$inject = ['$scope', '$location', '$routeParams', '$http'];