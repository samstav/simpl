'use strict'

// environments/
function EnvironmentListCtrl($scope, $location, Environment) {
	$scope.environments = Environment.query();

  $scope.provider_count = function(environment) {
    return Object.keys(environment.providers).length
  }

  $scope.create = function() {
    $location.path('/environments/new');
  }
}
EnvironmentListCtrl.$inject = ['$scope', '$location', 'Environment']; 


// environments/:environmentId
function EnvironmentDetailCtrl($scope, $location, $routeParams, Environment) {
  if ($routeParams.environmentId != "new") {
    $scope.environment = Environment.get({environmentId: $routeParams.environmentId});  
  } else {
    $scope.environment = {};
  }

  $scope.update = function(environment) {
    $scope.environment = angular.copy(environment);
    $scope.environment.$save();
    $location.path('/environments');
  }

  $scope.reset = function() {
    $scope.environment = Environment.get({environmentId: $routeParams.environmentId});
  }
}
EnvironmentDetailCtrl.$inject = ['$scope', '$location', '$routeParams', 'Environment']; 


function AuthCtrl($scope, $location) {
  $scope.auth = {
    username: '',
    password: '',
    catalog: null
  };

  $scope.authenticated = function() {
    return $scope.auth.catalog != null;
  }

  $scope.authenticate = function() {
  }

}
AuthCtrl.$inject = ['$scope', '$location']