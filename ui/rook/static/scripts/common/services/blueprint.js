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
      reset: function() {
        delete this.get().services;
        this.broadcast();
      },
      add: function(component, target) {
        // Add item to blueprint data.
        this.sort(component, target);
      },
      remove: function(selection) {
        var services = this.get().services;
        var service = services[selection.service];
        var component = service.component
        var components = service.components;

        if(component) {
          delete this.get().services[selection.service];
        } else if(components) {
          // Remove component to blueprint data.
          components.splice(selection.index, 1);

          // If the service has no components, remove the service.
          if(components.length < 1) {
            delete service
          }

          // Find all connections to the removed component and remove them.
          _.each(services, function(_service, _id, _services) {
            var i = _service.relations ? _service.relations.length : 0;

            while (i--) {
              _.each(_service.relations[i], function(_componentId, _serviceId) {
                if(_serviceId == selection.service) {
                  delete _service.relations[i];
                };
              });

              if(_.isEmpty(_service.relations[i])) {
                _service.relations.splice(i, 1);
              }

              if(!_service.relations.length) {
                delete _service.relations;
              }
            }
          });

          if(!service.components.length) {
            delete service.components;
            delete service.relations;
          }
        }

        if(_.isEmpty(service)) {
          delete this.get().services[selection.service];
        }

        if(_.isEmpty(services)) {
          delete this.get().services;
        }

        this.broadcast();
      },
      sort: function(component, target) {
        var serviceName = 'default';

        if (component && component.is) {
          serviceName = component.is;
        }

        if (typeof this.data.services === 'undefined') {
          this.data.services = {};
        }

        // disabling this for now
        //this.addComponent(component, serviceName);
        this.addComponentSingletons(component, serviceName);

        this.broadcast();
      },
      canConnect: function(source, target, protocol, optionalTag) {
        if(!source || !target || (source.componentId == target.componentId)) {
          return false;
        }

        var _connection;
        var _req;
        var _prov;
        var valid;
        var _interfaceIndex;
        var components = Catalog.getComponents();
        var connections = [];
        var requires = components[source.componentId].requires || [];
        var uses = components[source.componentId].supports || [];
        var interfaces = requires.concat(uses);

        // Find interface match in source requires and target provides
        _.each(interfaces, function(_requirement, index) {
          _req = {
            type: _.keys(_requirement)[0],
            interface: null
          };

          _connection = {
            type: _req.type,
            interface: null
          };

          if(_.isObject(_.values(_requirement)[0])) {
            if(_req.type == '*') {
              _req.interface = _.values(_requirement)[0];
            } else {
              _.extend(_req, _.values(_requirement)[0]);
            }
          } else {
            _req.interface = _.values(_requirement)[0];
            _connection.interface = _req.interface;
          }

          _.each(components[target.componentId].provides, function(_provided, index) {
            valid = false;

            _prov = {
              type: _.keys(_provided)[0],
              interface: null
            };

            if(_.isObject(_.values(_provided)[0])) {
              _.extend(_prov, _.values(_provided)[0]);
            } else {
              _prov.interface = _.values(_provided)[0];
            }

            if(_.isObject(_req.interface) && 'from' in _req.interface) {
              _interfaceIndex = _req.interface.from.indexOf(_prov.interface);

              if(_interfaceIndex > -1) {
                _connection.interface = _req.interface.from[_interfaceIndex];
                if(_req.connection_type) {
                  _connection['connect-from'] = _req.type;
                }
                valid = true;
              }
            }

            if(_req.interface == _prov.interface) {
              valid = true;
            }

            if(valid) {
              connections.push(_connection);
            }
          });
        });

        return connections.length ? connections : false;
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
        var _id = component.id || component.name;
        return this.getComponent(serviceName, _id) ? true : false;
      },
      getComponent: function(serviceId, componentId) {
        var components = ((this.data.services || {})[serviceId] || {}).components || [];

        var component = _.find(components, function(_component) {
          return _component.id == componentId || _component.name == componentId;
        });

        return component;
      },
      getComponentConstraints: function(serviceId, componentId) {
        return this.getComponent(serviceId, componentId).constraints || [];
      },
      saveComponentConstraints: function(data) {
        var _id = data.component.id || data.component.name;

        this.getComponent(data.serviceId, _id).constraints = data.constraints;
        this.broadcast();
      },
      addComponentToService: function(component, serviceName) {
        var _component = {};

        if('id' in component) {
          _component.id = component.id;
        } else if('name' in component) {
          _component.name = component.name;
        } else {
          throw new Error('Components require an id or name property to be added to a blueprint.');
        }

        this.data.services[serviceName].components.push(_component);
      },
      addService: function(serviceName, firstComponent) {
        this.data.services[serviceName] = {components: []};

        if(firstComponent) {
          this.addComponentToService(firstComponent, serviceName);
        }
      },
      broadcast: function() {
        $rootScope.$broadcast('blueprint:update', this.data);
      }
    };
  });
