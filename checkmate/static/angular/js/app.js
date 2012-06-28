angular.module('checkmate', ['checkmateFilters', 'checkmateServices', 'ngSanitize'])
  .config(['$routeProvider', function($routeProvider) {
    $routeProvider.
        when('/environments', {templateUrl: 'partials/environment-list.html',   controller: EnvironmentListCtrl}).
        when('/environments/:environmentId', {templateUrl: 'partials/environment-detail.html', controller: EnvironmentDetailCtrl}).
        when('/profile', {templateUrl: 'partials/profile.html', controller: ProfileCtrl}).
        when('/blueprints', {templateUrl: 'partials/blueprint-list.html', controller: BlueprintListCtrl}).
        when('/blueprints/:blueprintId', {templateUrl: 'partials/blueprint-detail.html', controller: BlueprintDetailCtrl}).
        when('/deployments', {templateUrl: 'partials/deployment-list.html', controller: DeploymentListCtrl}).
        when('/deployments/new', {templateUrl: 'partials/deployment-new.html', controller: DeploymentNewCtrl}).
        otherwise({redirectTo: '/'});
  }])
  .config(['$locationProvider', function($locationProvider) {
    //$locationProvider.html5Mode(true).hashPrefix('!');
  }]);



// TODO: REMOVE THIS, DEVELOPMENT ONLY
SETTINGS = {
  "options": {
    "username": {
      "regex": "xxx", 
      "required": "generatable", 
      "type": "string", 
      "description": "The user name used to access all resources in this deployment", 
      "label": "Admin"
    }, 
    "instance_os": {
      "constrains": [
        {
          "setting": "os", 
          "service": "web", 
          "resource_type": "compute"
        }
      ], 
      "group": "advanced", 
      "description": "The operating system of web servers.", 
      "default": "1", 
      "type": "select",
      "options": [
        {
          "name": "Ubuntu 12.04 LTS", 
          "value": 1
        }, 
        {
          "name": "Ubuntu 10.04 LTS", 
          "value": 2
        }
      ],
      "label": "Instance OS"
    }, 
    "domain": {
      "regex": "xxx", 
      "type": "string", 
      "description": "The domain you wish to host your blog on. (ex: http://example.com)", 
      "label": "Domain"
    }, 
    "secure": {
      "type": "boolean", 
      "description": "Make this a hardened deployment (you lose some flexibility)", 
      "label": "secure"
    }, 
    "instance_count": {
      "constrains": [
        {
          "setting": "count", 
          "service": "web", 
          "resource_type": "compute"
        }
      ], 
      "description": "The number of instances for the specified task.", 
      "default": 2, 
      "constraints": [
        {
          "greater-than": 1
        }
      ], 
      "type": "number", 
      "label": "Number of Instances"
    }, 
    "instance_flavor": {
      "default": 1024, 
      "label": "Instance Size", 
      "type": "uri", 
      "description": "The size of the instance in MB of RAM.", 
      "uri": "/577366/providers/...?type=type"
    }, 
    "database_size": {
      "default": 20, 
      "label": "Database Size", 
      "type": "uri", 
      "description": "The hard drive space available for the database instance in GB.", 
      "uri": "/577366/providers/...?type=type"
    }, 
    "ssl": {
      "default": true, 
      "type": "boolean", 
      "description": "Use SSL to encrypt web traffic.", 
      "label": "SSL Enabled"
    }, 
    "sample": {
      "constrains": [
        {
          "setting": "foo", 
          "service": "web", 
          "resource_type": "compute"
        }
      ], 
      "group": "advanced", 
      "description": "The operating system of web servers.", 
      "default": "Ubuntu 12.04", 
      "type": "uri", 
      "uri": "/577366/providers/...?type=type", 
      "label": "Instance OS"
    }, 
    "password": {
      "regex": "xxx", 
      "type": "string", 
      "description": "Password to use for service. Click the generate button to generate a random password.", 
      "label": "Password"
    }, 
    "high_availability": {
      "type": "boolean", 
      "description": "Insures your blog has higher uptimes by using redundant hardware (e.g. multuple servers)", 
      "label": "High Availability"
    }
  }
}