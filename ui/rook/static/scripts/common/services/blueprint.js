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
  },
  services: null
};

angular.module('checkmate.Blueprint', [
  'checkmate.Catalog'
]);

angular.module('checkmate.Blueprint')
  .factory('Blueprint', function($rootScope, Catalog, $timeout) {
    return {
      data: angular.copy(window.defaultBlueprint),
      get: function() {
        return this.data;
      },
      set: function(blueprint) {
        if(this.isValid(blueprint)) {
          this.data = angular.copy(blueprint);
          this.broadcast();
        }
      },
      reset: function() {
        this.set(defaultBlueprint);
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
      revert: function(component, target) {
        this.broadcast();
      },
      sever: function(data) {
        var relations = this.get().services[data.source].relations;
        var updated = _.reject(relations, function(relation) {
          var _target = _.keys(relation)[0]; // TODO: Account for long-hand relation.
          var _interface = _.values(relation)[0]; // TODO:  Account for long-hand relation.

          return (data.target == _target) && (data.interface == _interface);
        });

        this.get().services[data.source].relations = updated;
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

        var components = Catalog.getComponents();
        var provides = components[target.componentId].provides || [];
        var requires = components[source.componentId].requires || [];
        var supports = components[source.componentId].supports || [];
        var interfaces = requires.concat(supports);

        var required = normalize(interfaces);
        var provided = normalize(provides);
        var connections = resolve(required, provided);

        /**
        * Converts an array of interfaces into a map.
        * @param {array} relations List of relations from a Catalog entry.
        * @return {object} Map of connection names to their interfaces.
        */
        function normalize(relations) {
          var _connections = {};

          _.each(relations, function(_relation, index) {
            var _name = _.keys(_relation)[0];
            var _interface = _.values(_relation)[0];
            var _type = null;

            if(!_.isObject(_interface) && _interface.indexOf('#') > -1) {
              _type = _name;
              _name = _interface.split('#')[1];
            } else {
              _type = _interface.resource_type;
            }

            if(_interface.from) {
              _interface = _interface.from;
            } else if(_interface.interface) {
              if(_interface.interface.from) {
                _interface = _interface.interface.from;
              } else {
                _interface = _interface.interface;
              }

            } else {
              _interface = _interface.split('#')[0];
            }

            if(!(_name in _connections)) {
              _connections[_name] = {};
              _connections[_name].interfaces = [];
              if(_type) {
                _connections[_name].type = _type;
              }
            }

            if(_.isArray(_interface)) {
              _.each(_interface, function(__interface) {
                add(_connections, _name, __interface);
              });
            } else {
              add(_connections, _name, _interface);
            }
          });

          /**
          * Pushes an interface object into a connections array if it doesn't exist.
          * @param {object} connections Map of all available connection interfaces.
          * @param {object} interface A possible new connection.
          * @return {boolean} If the addition was successful.
          */
          function add(connections, name, interface) {
            var connection = connections[name].interfaces;

            if(connection.indexOf(interface) < 0) {
              connection.push(interface);
              return true;
            }

            return false;
          }

          return _connections;
        }

        /**
        * Finds valid connections between two interface objects.
        * @param {object} required A map of normalized interface connections.
        * @param {object} provided A map of normalized interface connections.
        * @return {array} A list of valid interfaces connections.
        */
        function resolve(required, provided) {
          var connections = [];

          _.each(required, function(_data, _type) {
            var _providesAll = (_type == '*');
            var _options = _providesAll ? provided : [_data];

            _.each(_options, function(_option, _index) {
              _.each(_option.interfaces, function(__interface, __index) {
                var __connection = {
                  type: null,
                  interface: null
                };

                if(!_.isArray(__interface)) {
                  __interface = [__interface];
                };

                _.each(__interface, function(___interface, ___index) {
                  var ___provided = provided[_data.type ? _data.type : _type];
                  var ___interfaces = ((___provided || {}).interfaces || []);
                  var ___acceptsAll = (___interface === '*');
                  var ___hasInterface = ___interfaces.indexOf(___interface) > -1;

                  if(___hasInterface || _providesAll || ___acceptsAll) {
                    if(!(___acceptsAll && _providesAll)) {
                      if(!_providesAll) {
                        __connection.type = _type;
                      }
                      __connection.interface = ___interface;

                      if(_data.type) {
                        __connection['connect-from'] = _data.type;
                      }
                    }
                  }
                });

                if(__connection.interface) {
                  connections.push(__connection);
                }
              });
            });

          });

          return connections;
        }

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
        if(!this.data.services) this.data.services = {};

        if (serviceName in this.data.services) {
          // disabling this for now: this.addComponentToService(component, serviceName);
          for(var i=2;i<25;i++) {
            var service = serviceName + i;
            var exists = this.data.services[service];
            var hasComponent = this.componentInService(component, service);

            if (!exists && !hasComponent) {
              this.addService(service, component);
              break;
            }
          }
        } else {
          this.addService(serviceName, component);
        }
      },
      addComponent: function(component, serviceName) { // Add each component allowing more than on in a service
        if(!this.data.services) this.data.services = {};

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
        var service = ((this.data.services || {})[serviceId] || {});
        var components = [];

        if(service.components) {
          components = service.components;
        } else if (service.component) {
          components = service.component;
        }

        var component = _.find(components, function(_component) {
          if(!_component) {
            return;
          }
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
      },
      isValid: function(blueprint) {
        var valid = true;

        if(!blueprint.name) valid = false;
        if(valid && !blueprint.version) valid = false;
        if(valid && !angular.isDefined(blueprint.services)) valid = false;

        if(valid) {
          _.each(blueprint.services, function(service, name) {
            var _hasName = name && name.length ? true : false;
            var _hasService = service ? true : false;
            var _hasComponent = 'component' in service && service.component ? true : false;
            var _hasComponents = 'components' in service && service.components.length > -1 ? true : _hasComponent;

            if(!_hasName || !_hasService || !_hasComponents) {
              valid = false;
              return valid;
            }
          });
        }

        if(!valid) {
          $rootScope.$broadcast('blueprint:invalid');
        } else {
          $rootScope.$broadcast('blueprint:valid');
        }

        return valid;
      }
    };
  });
