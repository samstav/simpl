angular.module('checkmate.Catalog', []);
angular.module('checkmate.Catalog')
  .factory('Catalog', function($rootScope, $http) {
    var Catalog = {
      'data': {},
      'components': {}
    };

    Catalog.get = function() {
      return this.data;
    };

    Catalog.set = function(data) {
      var components = {};

      // This sets the component map.
      angular.forEach(data, function(_components, _service) {
        angular.forEach(_components, function(_component) {
          components[_component.id || _component.name] = _component;
        });
      });

      this.components = angular.extend(this.components, components);
      this.data = data;

      Catalog.broadcast();
    };

    Catalog.getComponents = function() {
      return this.components;
    };

    Catalog.getComponent = function(name) {
      return this.components[name];
    };

    Catalog.broadcast = function() {
      $rootScope.$broadcast('catalog:update', this.data);
    };

    Catalog.fromUrl = function(url) {
      $http.get(url).
        success(function(data, status, headers, config) {
          try {
            var parsed = {};

            jsyaml.safeLoadAll(data, function(doc) {
              var category = doc.is || 'other';

              if (!(category in parsed)) {
                parsed[category] = {};
              }

              parsed[category][doc.id || doc.name] = doc;
            });

            Catalog.set(parsed);
          } catch(err) {
            console.log("YAML file for Blueprint documentation could not be parsed", err);
          }

        }).
        error(function(data, status, headers, config) {
          // called asynchronously if an error occurs
          // or server returns response with an error status.
          console.error(data, status, headers(), config);
        });
    };

    Catalog.fromUrl('/scripts/common/services/catalog.yml');

    return Catalog;
  });
