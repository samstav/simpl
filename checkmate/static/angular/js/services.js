angular.module('checkmateServices', ['ngResource']).
factory('Environment', function($resource) {
  return $resource('/:tenantId/environments/:environmentId', {
    environmentId: '@id',
    tenantId: cm.auth.getTenant()
  }, {
    query: {
      method: 'GET',
      url: '/:tenantId/environments',
      params: {
        tenantId: cm.auth.getTenant()
      },
      isArray: true,
      headers: {"X-Auth-Token": cm.auth.getToken()}
    },
    update: {
      method: 'PUT'
    }
  });
}).
factory('Blueprint', function($resource) {
  return $resource('/blueprints/:blueprintId', {
    blueprintId: '@id'
  }, {
    query: {
      method: 'GET',
      url: '/blueprints',
      params: {
        tenantId: cm.auth.getTenant()
      },
      isArray: true
    },
    update: {
      method: 'PUT'
    }
  })
}).
factory('Deployment', function($resource) {
  return $resource('/deployments/:deploymentId', {
    deploymentId: '@id'
  }, {
    query: {
      method: 'GET',
      url: '/deployments',
      isArray: true
    },
    update: {
      method: 'PUT'
    }
  })
});