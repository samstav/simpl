angular.module('checkmateServices', ['ngResource']).
  factory('Environment', function($resource) {
    return $resource('/environments/:environmentId', {environmentId:'@id'}, {
      query: {method:'GET', url:'/environments', isArray:true},
      update: {method: 'PUT'}      
    });
  }).
  factory('Blueprint', function($resource) {
    return $resource('/blueprints/:blueprintId', {blueprintId: '@id'}, {
      query: {method: 'GET', url:'/blueprints', isArray:true},
      update: {method: 'PUT'}
    })
  }).
  factory('Deployment', function($resource) {
    return $resource('/deployments/:deploymentId', {deploymentId: '@id'}, {
      query: {method: 'GET', url:'/deployments', isArray:true},
      update: {method: 'PUT'}
    })
  });
