var defaultDeployment = {
  environment: {
    "name": "Next-Gen Open Cloud",
    "providers": {
      "chef-server": {
        "vendor": "opscode",
        "constraints": [
          {
            "source": "https://github.com/gondoi/phpstack#applications"
          }
        ]
      },
      "load-balancer": {},
      "nova": {},
      "common": {
        "vendor": "rackspace"
      }
    }
  },
  inputs: {}
};

angular.module('checkmate.DeploymentData', [
  'checkmate.Blueprint',
  'checkmate.codemirror'
]);
angular.module('checkmate.DeploymentData')
  .factory('DeploymentData', function($rootScope, Blueprint){
    var service = {
      data: $.extend(window.defaultDeployment, {blueprint: Blueprint.get()}),
      get: function() {
        return this.data;
      },
      set: function(deployment) {
        this.data = angular.copy(deployment);
        Blueprint.set(this.data.blueprint);
        this.broadcast();
      },
      broadcast: function() {
        $rootScope.$broadcast('deployment:update', this.data);
      }
    };
    $rootScope.$on('blueprint:update', function(event, data) {
      service.data.blueprint = data;
      service.broadcast();
    });
    return service;
  });
