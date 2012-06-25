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

  $scope.navigate = function(environmentId) {
    $location.path('/environments/' + environmentId);
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
      async: false,
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
    });
  }
}
AuthCtrl.$inject = ['$scope', '$location']

function ProfileCtrl($scope, $location) {

}
ProfileCtrl.$inject = ['$scope', '$location'];