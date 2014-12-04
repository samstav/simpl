var defaultBlueprint = {
  name: 'PowerStack Demo',
  version: '1.0.0',
  options: {},
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

        if (component.is) {
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
        var fromServiceId = from.serviceId,
            fromComponentId = from.componentId;
        var targetServiceId = target.serviceId,
            targetComponentId = target.componentId;
        if (!(fromServiceId in this.data.services)) {
          return false;
        }
        if (!(targetServiceId in this.data.services)) {
          return false;
        }
        var fromService = this.data.services[fromServiceId];
        var targetService = this.data.services[targetServiceId];
        return true;
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
