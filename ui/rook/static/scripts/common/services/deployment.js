var defaultDeployment = {
  environment: {
    "name": "Next-Gen Open Cloud",
    "providers": {
      "chef-server": {
        "vendor": "opscode",
        "constraints": [
          {
            "source": "https://github.com/AutomationSupport/catalog"
          }
        ]
      },
      "load-balancer": {},
      "nova": {},
      "database": {},
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
        if(this.isValid(deployment)) {
          this.data = angular.copy(deployment);

          if(Blueprint.isValid(this.data.blueprint)) {
            Blueprint.set(this.data.blueprint);
          } else {
            this.data.blueprint = Blueprint.get();
          }

          this.broadcast();
        }
      },
      broadcast: function() {
        $rootScope.$broadcast('deployment:update', this.data);
      },
      isValid: function(deployment) {
        var valid = true;
        var env = deployment.environment;
        var blueprint = deployment.blueprint;

        if(!env) valid = false;
        if(valid && !env.name) valid = false;
        if(valid && !env.providers) valid = false;
        if(valid && !blueprint) valid = false;
        if(valid && !Blueprint.isValid(blueprint)) valid = false;

        if(!valid) {
          $rootScope.$broadcast('deployment:invalid');
        } else {
          $rootScope.$broadcast('deployment:valid');
        }

        return valid;
      }
    };

    $rootScope.$on('blueprint:update', function(event, data) {
      service.data.blueprint = data;
      service.broadcast();
    });

    return service;
  });
