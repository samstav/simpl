checkmate = angular.module('checkmate', ['checkmateFilters', 'checkmateServices', 'ngSanitize'])

checkmate.config(['$routeProvider', function($routeProvider) {
  $routeProvider.
  when('/environments', {
    templateUrl: 'partials/environment-list.html',
    controller: EnvironmentListCtrl
  }).
  when('/environments/:environmentId', {
    templateUrl: 'partials/environment-detail.html',
    controller: EnvironmentDetailCtrl
  }).
  when('/profile', {
    templateUrl: 'partials/profile.html',
    controller: ProfileCtrl
  }).
  when('/blueprints', {
    templateUrl: 'partials/blueprint-list.html',
    controller: BlueprintListCtrl
  }).
  when('/blueprints/:blueprintId', {
    templateUrl: 'partials/blueprint-detail.html',
    controller: BlueprintDetailCtrl
  }).
  when('/deployments', {
    templateUrl: 'partials/deployment-list.html',
    controller: DeploymentListCtrl
  }).
  when('/deployments/new', {
    templateUrl: 'partials/deployment-new.html',
    controller: DeploymentNewCtrl
  }).
  when('/deployments/:deploymentId/status', {
    templateUrl: 'partials/deployment-status.html',
    controller: DeploymentStatusCtrl
  }).
  otherwise({
    redirectTo: '/'
  });
}]);

checkmate.directive('compileHtml', function($compile) {
  return {
    restrict: 'A',
    scope: {
      compileHtml: '='
    },
    replace: true,

    link: function(scope, element, attrs) {
      scope.$watch('compileHtml', function(value) {
        element.html($compile(value)(scope.$parent));
      });
    }
  }
});


// TODO: Make this more permanent
var cm = cm ? cm : {};
cm.auth = (function() {
  var serviceCatalog = null;

  function setServiceCatalog(sc) {
    serviceCatalog = sc;
  }

  function getToken() {
    if (serviceCatalog == null) {
      return null;
    }

    return serviceCatalog.access.token.id;
  }

  function getTenant() {
    if (serviceCatalog == null) {
      return null;
    }

    return serviceCatalog.access.token.tenant.id;
  }

  function isAuthenticated() {
    if (serviceCatalog == null) {
      return false;
    }

    var expires = new Date(serviceCatalog.access.token.expires);
    var now = new Date();

    if (expires < now) {
      return false;
    }

    return true;
  }

  return {
    setServiceCatalog: setServiceCatalog,
    getToken: getToken,
    getTenant: getTenant,
    isAuthenticated: isAuthenticated
  }
}());

cm.Resource = (function() {

  function query($http, resource) {
    return $http({
      method: 'GET',
      url: tenantUri() + resource,
      headers: headers()
    });
  }

  function get($http, resource, id) {
    return $http({
      method: 'GET',
      url: tenantUri() + resource + '/' + id,
      headers: headers
    });
  }

  function saveOrUpdate($http, resource, instance) {
    if (instance.id == null) {
      return $http({
        method: 'POST',
        url: tenantUri() + resource,
        headers: headers,
        data: JSON.stringify(instance)
      });

    } else {
      return $http({
        method: 'PUT',
        url: tenantUri() + resource + '/' + instance.id,
        headers: headers,
        data: JSON.stringify(instance)
      });
    }
  }

  function del($http, resource, instance) {
    return $http({
      method: 'DELETE',
      url: tenantId() + resource + '/' + instance.id,
      headers: headers()
    });
  }

  // Privates

  function tenantUri() {
    return '/' + cm.auth.getTenant() + '/';
  }

  function headers() {
    return {
      "X-Auth-Token": cm.auth.getToken()
    };
  }

  return {
    query: query,
    get: get,
    saveOrUpdate: saveOrUpdate,
    del: del
  }
}());

cm.Settings = (function() {

  function getSettingsFromBlueprint(bp) {
    var options = new Array(); // The accumulating array

    var opts = bp.options;
    _.each(opts, function(option, key) {
      options.push($.extend({
        id: key
      }, option));
    });

    _.each(options, function(option) {
      if (option.regex) {
        if (!_.isRegExp(option.regex)) {
          console.log("Regex '" + option.regex + "' is invalid for setting " + option.id);
          delete option["regex"];
        }
      }
    });

    return options;
  }

  function getSettingsFromEnvironment(env) {

  }


  return {
    getSettingsFromBlueprint: getSettingsFromBlueprint,
    getSettingsFromEnvironment: getSettingsFromEnvironment
  }
}());

PROVIDERS = {
  compute: {
    label: "Compute",
    options: [{
      id: "0505af50-a38d-012f-ead2-583062589e95",
      name: "Legacy Cloud Servers"
    }, {
      id: "19691970-a38d-012f-ead3-583062589e95",
      name: "Open Cloud Servers"
    }]
  },
  database: {
    label: "Database",
    options: [{
      id: "6701f550-a38d-012f-ead4-583062589e95",
      name: "Database as a Service"
    }, {
      id: "89632410-a38d-012f-ead5-583062589e95",
      name: "Open Cloud Servers"
    }]
  },
  lb: {
    label: "Load Balancing",
    options: [{
      id: "0000f550-a38d-012f-ead4-583062589e95",
      name: "Load Balancer as a Service"
    }, {
      id: "8643c410-a38d-012f-ead5-583062589e95",
      name: "Open Cloud Servers"
    }]
  }
}