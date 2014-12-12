var defaultBlueprint = {
  name: 'PowerStack Demo',
  version: '1.0.0',
  options: {
    "chef-server-username": {
      "constrains": [
        {
          "setting": "server-username",
          "provider": "chef-server"
        }
      ],
      "display-hints": {
        "group": "chef",
        "order": 2
      },
      "type": "string"
    },
    "validator-username": {
      "constrains": [
        {
          "setting": "validator-username",
          "provider": "chef-server"
        }
      ],
      "display-hints": {
        "group": "chef",
        "order": 5
      },
      "type": "string"
    },
    "server_size": {
      "constrains": [
        {
          "setting": "memory",
          "resource_type": "compute"
        }
      ],
      "help": "Server sizes are based on amount of RAM allocated to the system. Disk\nspace will be dependent on server flavors available in the region\nselected. By default, we will build the best performing server\navailable.\n",
      "default": 1024,
      "description": "The size of the web servers in MB of RAM.",
      "label": "Server Size",
      "display-hints": {
        "group": "server",
        "list-type": "compute.memory",
        "order": 3,
        "choice": [
          {
            "name": "1 GB",
            "value": 1024
          },
          {
            "name": "2 GB",
            "value": 2048
          },
          {
            "name": "4 GB",
            "value": 4096
          },
          {
            "name": "8 GB",
            "value": 8192
          },
          {
            "name": "15 GB",
            "value": 15360
          },
          {
            "name": "30 GB",
            "value": 30720
          }
        ]
      },
      "type": "integer",
      "constraints": [
        {
          "message": "must be 1024 or larger",
          "greater-than-or-equal-to": 1024
        },
        {
          "message": "must be 30720 or smaller",
          "less-than-or-equal-to": 30720
        }
      ]
    },
    "region": {
      "constrains": [
        {
          "setting": "region",
          "provider": "load-balancer"
        },
        {
          "setting": "region",
          "provider": "nova"
        }
      ],
      "display-hints": {
        "group": "deployment",
        "list-type": "region",
        "choice": [
          "DFW",
          "IAD",
          "ORD",
          "LON",
          "SYD",
          "HKG"
        ]
      },
      "default": "ORD",
      "required": true,
      "type": "string",
      "label": "Region"
    },
    "chef-server-url": {
      "constrains": [
        {
          "setting": "server-url",
          "provider": "chef-server"
        }
      ],
      "display-hints": {
        "group": "chef",
        "order": 1
      },
      "type": "url",
      "label": "Chef Server Org URL"
    },
    "chef-server-user-key": {
      "constrains": [
        {
          "setting": "server-user-key",
          "provider": "chef-server"
        }
      ],
      "display-hints": {
        "group": "chef",
        "order": 3
      },
      "type": "text"
    },
    "os": {
      "constrains": [
        {
          "setting": "os",
          "resource_type": "compute"
        }
      ],
      "help": "Required: The operating system for the host server.\n",
      "default": "Ubuntu 14.04",
      "description": "The operating system for the host server.\n",
      "label": "Operating System",
      "display-hints": {
        "group": "server",
        "list-type": "compute.os",
        "order": 2,
        "choice": [
          {
            "name": "Ubuntu 14.04 LTS (Precise Pangolin)",
            "value": "Ubuntu 14.04"
          },
          {
            "name": "CentOS 7",
            "value": "CentOS 7"
          }
        ]
      },
      "type": "string",
      "constraints": [
        {
          "message": "must be a supported operating system",
          "in": [
            "Ubuntu 14.04",
            "CentOS 7"
          ]
        }
      ]
    },
    "validator-pem": {
      "constrains": [
        {
          "setting": "validator-pem",
          "provider": "chef-server"
        }
      ],
      "display-hints": {
        "group": "chef",
        "order": 4
      },
      "type": "text"
    }
  },
  'meta-data': {
      'schema-version': 'v0.7',
      'reach-info': {
        'option-groups': ['application']
      }
  }
};

angular.module('checkmate.Blueprint', [
  'checkmate.Catalog'
]);
angular.module('checkmate.Blueprint')
  .factory('Blueprint', function($rootScope, Catalog) {
    return {
      data: window.defaultBlueprint,
      get: function() {
        return this.data;
      },
      set: function(blueprint) {
        this.data = angular.copy(blueprint);
        this.broadcast();
      },
      add: function(component, target) {
        // Add item to blueprint data.
        this.sort(component, target);
      },
      sort: function(component, target) {
        var serviceName = 'default';

        if (component && component.is) {
          serviceName = component.is;
        }

        if (typeof this.data.services === 'undefined') {
          this.data.services = {};
        }

        // disabling this for now: this.addComponent(component, serviceName);
        this.addComponentSingletons(component, serviceName);

        this.broadcast();
      },
      canConnect: function(from, target, protocol, optionalTag) {
        var isValid = false;
        var catalog = {
          source: Catalog.getComponent(from.componentId) || [],
          target: Catalog.getComponent(target.componentId) || []
        };
        var map = {
          provides: {},
          requires: {}
        };

        for (var i = 0; i < catalog.source.requires.length; i++) {
          _.extend(map.requires, catalog.source.requires[i]);
        }

        for (var j = 0; j < catalog.target.provides.length; j++) {
          _.extend(map.provides, catalog.target.provides[j]);

          _.each(catalog.target.provides[j], function(val, key) {
            if(map.requires[key] && map.requires[key] == val) {
              isValid = true;
            }
          });
        }

        if(!protocol && isValid) {
          return isValid;
        }

        return isValid;
      },
      connect: function(fromServiceId, toServiceId, protocol, optionalTag) {
        var fromService = this.data.services[fromServiceId];

        if (!angular.isArray(fromService.relations)) {
          fromService.relations = [];
        }

        var relation = {};

        if (typeof optionalTag === 'string' && optionalTag.length > 0) {
          relation[toServiceId] = protocol + '#' + optionalTag;
        } else {
          relation[toServiceId] = protocol;
        }

        if (typeof _.findWhere(fromService.relations, relation) === 'undefined') {
          fromService.relations.push(relation);
          this.broadcast();
        }
      },
      addComponentSingletons: function(component, serviceName) {  // Add each component in its own service
        if (serviceName in this.data.services) {
          // disabling this for now: this.addComponentToService(component, serviceName);
          for(var i=2;i<25;i++) {
             if (!this.componentInService(component, serviceName + i)) {
              this.addService(serviceName + i, component);
              break;
            }
          }
        } else {
          this.addService(serviceName, component);
        }
      },
      addComponent: function(component, serviceName) { // Add each component allowing more than on in a service
        if (serviceName in this.data.services) {
          if (!this.componentInService(component, serviceName)) {
            this.addComponentToService(component, serviceName);
          } else {
            return;
          }
        } else {
          this.addService(serviceName, component);
        }
      },
      componentInService: function(component, serviceName) {
        return this.data.services && serviceName in this.data.services && this.data.services[serviceName].components.indexOf(component.id) > -1;
      },
      addComponentToService: function(component, serviceName) {
        this.data.services[serviceName].components.push(component.id);
      },
      addService: function(serviceName, firstComponent) {
        this.data.services[serviceName] = {
          annotations: {},
          components: [firstComponent.id]
        };
      },
      broadcast: function() {
        $rootScope.$broadcast('blueprint:update', this.data);
      }
    };
  });
