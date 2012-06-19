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
EnvironmentListCtrl.$inject = ['$scope', '$location', 'Environment']; // Needed to keep minification from breaking things


// environments/:environmentId
function EnvironmentDetailCtrl($scope, $routeParams, Environment) {
  if ($routeParams.environmentId != "new") {
    $scope.environment = Environment.get({environmentId: $routeParams.environmentId});  
  }
}
EnvironmentDetailCtrl.$inject = ['$scope', '$routeParams', 'Environment']; // Needed to keep minification from breaking things
