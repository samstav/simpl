'use strict'

/**
 *   environments
 */

function EnvironmentListCtrl($scope, $location, $http, Environment) {

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
EnvironmentListCtrl.$inject = ['$scope', '$location', '$http', 'Environment'];

/**
 *   environments/:environmentId
 */

function EnvironmentDetailCtrl($scope, $location, $http, $routeParams, Environment) {
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

    /*
    $scope.environment = Environment.get({environmentId: $routeParams.environmentId}, function() {
      
      // If we have some selected providers already
      if ($scope.environment.providers) {
        // For each selected provider, we set the selected properties
        _.each($scope.environment.providers, function(selected, key) {
          var p = _.find($scope.providers, function(provider) { 
            if (provider.id == key) { return provider; } 
          });
          $scope.selectedProviders[key] = p;
        });
      }
    });  
    */
  } else {
    $scope.environment = new Environment();
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
EnvironmentDetailCtrl.$inject = ['$scope', '$location', '$http', '$routeParams', 'Environment'];

/**
 *   blueprints
 */

function BlueprintListCtrl($scope, $location, $http, Blueprint) {
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
BlueprintListCtrl.$inject = ['$scope', '$location', '$http', 'Blueprint']

/**
 *   blueprints
 */

function BlueprintDetailCtrl($scope, $location, $routeParams, Blueprint) {
  if ($routeParams.blueprintId != "new") {
    $scope.blueprint = Blueprint.get({
      blueprintId: $routeParams.blueprintId
    }, function() {
      $scope.stringify = JSON.stringify($scope.blueprint, null, '\t');
      $scope.codeMirror = CodeMirror.fromTextArea($('#editor').get(0), {
        value: $scope.stringify,
        mode: 'javascript',
        lineNumbers: true
      });
    });
  } else {
    $scope.blueprint = new Blueprint();
    $scope.stringify = "{ }"
  }


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
BlueprintDetailCtrl.$inject = ['$scope', '$location', '$routeParams', 'Blueprint']

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
  cm.Resource.query($http, 'deployments')
    .success(function(data, status) {
      $scope.deployments = data;
    });

  $scope.delete = function(deployment) {
    cm.Resource.del($http, 'deployments', deployment)
      .success(function(data, status) {
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
      $scope.settings.push(cm.Settings.getSettingsFromBlueprint($scope.blueprint));
    }

    if ($scope.environment) {
      $scope.settings.push(cm.Settings.getSettingsFromEnvironment($scope.environment));
    }

    $scope.settings = _.flatten($scope.settings, true); // combine everything to one array
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

    return template ? Mustache.render(template, setting) : "";
  }

  $scope.submit = function() {
    var deployment = {};

    deployment.blueprint = $scope.blueprint;
    deployment.environment = $scope.environment;
    deployment.inputs = $scope.answers;

    cm.Resource.saveOrUpdate($http, 'deployments', deployment)
      .success(function(data, status) {
        $location('/deployment/' + data.id);
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