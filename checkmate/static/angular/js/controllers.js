'use strict'

/**
  *   environments
  */
function EnvironmentListCtrl($scope, $location, Environment) {
	$scope.environments = Environment.query();

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
EnvironmentListCtrl.$inject = ['$scope', '$location', 'Environment']; 

/**
  *   environments/:environmentId
  */
function EnvironmentDetailCtrl($scope, $location, $routeParams, Environment) {
  if ($routeParams.environmentId != "new") {
    $scope.environment = Environment.get({environmentId: $routeParams.environmentId});  
  } else {
    $scope.environment = new Environment();
  }

  $scope.update = function(environment) {
    $scope.environment = angular.copy(environment);

    if ($scope.environment.id == null) {
      $scope.environment.$save();
    } else {
      $scope.environment.$update();
    }
    
    $location.path('/environments');
  }

  $scope.reset = function() {
    $scope.environment = Environment.get({environmentId: $routeParams.environmentId});
  }
}
EnvironmentDetailCtrl.$inject = ['$scope', '$location', '$routeParams', 'Environment']; 

/**
  *   blueprints
  */
function BlueprintListCtrl($scope, $location, Blueprint) {
  $scope.blueprints = Blueprint.query();

  $scope.serviceList = function(blueprint) {
    return blueprint.services ? Object.keys(blueprint.services).join(', ') : 0;
  }

  $scope.detail = function(blueprintId) {
    $location.path('/blueprints/' + blueprintId);
  }

  $scope.newDeployment = function(blueprintId) {
    $location.path('/deployments/new').search({blueprintId: blueprintId});
  }

}
BlueprintListCtrl.$inject = ['$scope', '$location', 'Blueprint']

/**
  *   blueprints
  */
function BlueprintDetailCtrl($scope, $location, $routeParams, Blueprint) {
  if ($routeParams.blueprintId != "new") {
    $scope.blueprint = Blueprint.get({blueprintId: $routeParams.blueprintId}, function() {
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
    $scope.blueprint = Blueprint.get({blueprintId: $routeParams.blueprintId});
  }


}
BlueprintDetailCtrl.$inject = ['$scope', '$location', '$routeParams', 'Blueprint']

/**
  *   Authentication
  */
function AuthCtrl($scope, $location) {
  $scope.auth = {
    username: '',
    password: '',
    catalog: null
  };

  var modal = $('#auth_modal');
  modal.modal({
    keyboard: false,
    show: true
  });

  $('#auth_modal').modal('show');

  $scope.authenticated = function() {
    return $scope.auth.catalog != null;
  }

  $scope.signOut = function() {
    $scope.auth = {
      username: '',
      password: '',
      catalog: null
    };
    $location('/');
  }

  $scope.authenticate = function() {
    $('#auth_loader').show();

    return $.ajax({
      type: "POST",
      contentType: "application/json; charset=utf-8",
      dataType: "json",
      url: "https://identity.api.rackspacecloud.com/v1.1/auth",
      data: JSON.stringify({
              "credentials": {
                "username": $scope.auth.username,
                "key": $scope.auth.password
              }
            }),
    }).always(function(json) {
      $scope.auth.catalog = json;
    }).success(function() {
      $('#auth_modal').modal('hide');
      $('#auth_loader').hide();
    }).error(function() {
      $("#auth_error_text").html("Something bad happened");
      $('#auth_loader').hide();
      $("#auth_error").show();

      //REMOVE THIS - DEVELOPMENT ONLY
      $scope.auth.catalog = '{}'
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
function DeploymentListCtrl($scope, $location, Deployment) {
  $scope.deployments = Deployment.query();

  $scope.delete = function(deoloyment) {
    deployment.$delete();
  }

  $scope.create = function() {
    $location.path('/deployments/new');
  }

  $scope.navigate = function(deploymentId) {
    $location.path('/deployments/' + deploymentId);
  }

}
DeploymentListCtrl.$inject = ['$scope', '$location', 'Deployment'];

/**
  *   Deployments
  */
function DeploymentNewCtrl($scope, $location, $routeParams, Deployment, Environment, Blueprint) {
  $scope.blueprints = Blueprint.query();
  $scope.environments = Environment.query();

  // Munge the settings so they have an id I can use.
  var s = new Array();
  for(var i in SETTINGS.options) { 
    s.push($.extend({id: i}, SETTINGS.options[i])) 
  }
  $scope.settings = s;

  $scope.renderSetting = function(setting) {
    var template = $('#setting-' + setting.type).html();

    if (template) {
      return Mustache.render(template, setting);
    } else {
      return "";
    }
  }
}
DeploymentNewCtrl.$inject = ['$scope', '$location', '$routeParams', 'Deployment', 'Environment', 'Blueprint'];
