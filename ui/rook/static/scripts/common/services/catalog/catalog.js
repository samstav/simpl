angular.module('checkmate.Catalog', []);
angular.module('checkmate.Catalog')
  .factory('Catalog', function($rootScope, $http, auth) {
    var Catalog = {
      'data': {},
      'components': {},
      'loading': false,
      'error': false
    };

    Catalog.get = function() {
      return this.data;
    };

    Catalog.hasError = function() {
      return Catalog.error;
    };

    Catalog.isLoading = function() {
      return Catalog.loading;
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

    Catalog.getDefaults = function() {
      var url = '/scripts/common/services/catalog/catalog.yml';
      var that = this;
      that.loading = true;

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
            that.loading = false;
          } catch(err) {
            console.log("YAML file for Blueprint documentation could not be parsed", err);
            that.loading = false;
          }

        }).
        error(function(data, status, headers, config) {
          // called asynchronously if an error occurs
          // or server returns response with an error status.
          console.error(data, status, headers(), config);
        });
    };

    Catalog.load = function() {
      var that = this;
      that.loading = true;

      if(auth.context.tenantId) {
        url = url = '/' + auth.context.tenantId + '/providers.json';

        $http.get(url).
          success(function(data, status, headers, config) {
            try {
              var parsed = {};

              _.each(data, function(item, key) {
                if(!parsed[item.name]) parsed[item.name] = {};
                parsed[item.name][key] = item;
              });

              Catalog.set(parsed);
              that.error = null;
            } catch(err) {
              that.error = "Provider response for Blueprint documentation could not be parsed";
              console.log(that.error, err);
            }

            that.loading = false;
          }).
          error(function(data, status, headers, config) {
            // called asynchronously if an error occurs
            // or server returns response with an error status.
            console.error(data, status, headers(), config);
            that.error = 'Responded with a ' + status;
            that.loading = false;
          });
      } else {
        that.getDefaults();
      }
    };

    return Catalog;
  });
