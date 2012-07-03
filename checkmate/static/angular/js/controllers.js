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
  // Munge the providers so they have an id I can use.
  var p = new Array();
  $scope.selectedProviders = {}
  for(var i in PROVIDERS) { 
    p.push($.extend({id: i, select: null}, PROVIDERS[i]));     
    $scope.selectedProviders[i] = null;
  }
  $scope.providers = p;

  if ($routeParams.environmentId != "new") {
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
      url: "/authproxy",
      data: JSON.stringify({
              "endpoint": "us",
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
  $scope.blueprints = Blueprint.query(function() {
    $scope.blueprintId = _.find($scope.blueprints, function(bp) { return bp.id == $routeParams.blueprintId });
  });
  $scope.environments = Environment.query();

  
  $scope.environmentId = null;
  $scope.setting = {};

  // Munge the settings so they have an id I can use.
  var s = new Array();
  for(var i in SETTINGS.options) { 
    s.push($.extend({id: i}, SETTINGS.options[i])) 
    $scope.setting[i] = null;
  }
  $scope.settings = s;

  $scope.renderSetting = function(setting) {
    var template = $('#setting-' + setting.type).html();
    return template ? Mustache.render(template, setting) : "";
  }

  $scope.submit = function() {
    var deployment = new Deployment();
    var blueprint = _.find($scope.blueprints, function(bp) { return bp.id == $scope.blueprintId });
    var environment = _.find($scope.environments, function(env) { return env.id == $scope.environmentId });

    
    deployment.blueprint = blueprint;
    deployment.environment = environment;

    deployment.$save();
  }
}
DeploymentNewCtrl.$inject = ['$scope', '$location', '$routeParams', 'Deployment', 'Environment', 'Blueprint'];
