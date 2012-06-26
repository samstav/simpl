angular.module('checkmate', ['checkmateFilters', 'checkmateServices', 'ngSanitize'])
  .config(['$routeProvider', function($routeProvider) {
    $routeProvider.
        when('/environments', {templateUrl: 'partials/environment-list.html',   controller: EnvironmentListCtrl}).
        when('/environments/:environmentId', {templateUrl: 'partials/environment-detail.html', controller: EnvironmentDetailCtrl}).
        when('/profile', {templateUrl: 'partials/profile.html', controller: ProfileCtrl}).
        when('/blueprints', {templateUrl: 'partials/blueprint-list.html', controller: BlueprintListCtrl}).
        otherwise({redirectTo: '/'});
  }])
  .config(['$locationProvider', function($locationProvider) {
    //$locationProvider.html5Mode(true).hashPrefix('!');
  }]);

