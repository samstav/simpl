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
  .factory('DeploymentData', function($rootScope, Blueprint, $http) {
    window.defaultDeployment.blueprint = Blueprint.get();

    var service = {
      data: angular.copy(window.defaultDeployment),
      export: function() {
        var deployment = this.get();
        var name = 'ye';
        var filetype;
        var filename = deployment.blueprint.name + ' - ' + (new Date()).getTime();
        var type = 'data:text/csv';
        var headers = [
          'charset=utf-8'
        ];
        var content;
        var href;
        var link = document.createElement("a");

        // Try to guess filetype.
        if(this.mime.indexOf('yaml') > -1) {
          deployment = jsyaml.safeDump(deployment);
          filetype = 'yaml';
        } else {
          deployment = JSON.stringify(deployment, undefined, 2);
          filetype = 'json';
        }

        // Set the content after we've tried to guess the type and format.
        content = escape(deployment);

        // Build a fake anchor tag to fake click later.
        href = type+';'+headers.join(',')+','+content;
        link.href = href;
        link.download = filename + '.' + filetype;

        // Simulate a click event on this new element to trigger download.
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      },
      get: function() {
        return this.data;
      },
      mime: null,
      save: function(tenantId, deployment, overwrite) {
        // If there's no blueprint, we can't save it.
        if(!deployment.blueprint) {
          console.error('no blueprint. :(');
          return;
        };

        // If there's no tenantId, we can't save it.
        if(!tenantId && isNaN(tenantId)) {
          console.error('no tenantId. :(');
          return;
        };

        // Remove the ID we generate a new one.
        if(!overwrite && deployment.id) {
          delete deployment.id;
        }

        var that = this;
        var req = {
          method: 'POST',
          url: '/' + tenantId + '/blueprints',
          data: deployment
        };

        return $http(req)
          .success(function(data, status, headers, config) {
            // Update the Deployment with the response (with new ID)
            var updated = that.get();
            updated.id = data.id;

            that.set(updated);
          }).error(function(data, status, headers, config) {
            console.error('Setting Deployment failed: ', data);
          });
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
      setMime: function(mime) {
        this.mime = mime;
      },
      reset: function() {
        Blueprint.reset();
        window.defaultDeployment.blueprint = Blueprint.get();
        this.set(window.defaultDeployment);
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
