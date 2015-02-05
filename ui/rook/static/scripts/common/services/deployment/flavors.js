angular.module('checkmate.Flavors', []);

angular.module('checkmate.Flavors')
  .directive('cmFlavorSelect', function() {
    return {
      restrict: 'EA',
      replace: true,
      controller: function($scope, Flavors) {
        $scope.flavors = Flavors;
      },
      template: '<select id="flavor" \
                          ng-model="flavors.selected" \
                          ng-change="flavors.select()" \
                          ng-options="flavor.id as flavor.name for flavor in flavors.list" \
                          required> \
                  </select>'
    };
  });

angular.module('checkmate.Flavors')
  .factory('Flavors', ['options', '$rootScope', '$route', '$location',
    function(options, $rootScope, $route, $location) {
      var flavors = {};

      flavors.data = null;
      flavors.list = [];
      flavors.default = {
        id: 'original',
        name: 'Original',
        weight: -1
      };
      flavors.selected = flavors.default.id;
      flavors.original = {};
      flavors.getFlavor = function(selected) {
        selected = selected || this.selected || this.default.id;
        return this.data[selected];
      };

      flavors.reset = function() {
        this.data = null;
        this.original = {};
      };

      flavors.select = function(selected) {
        var copy = angular.copy(this.original);
        var blueprint;

        if(selected) {
          this.selected = selected;
        }

        if(this.selected !== this.default.id) {
          blueprint = options.extendDeep(copy.blueprint, this.getFlavor().blueprint);
          $location.search('flavor', this.selected);
        } else {
          blueprint = copy.blueprint;
          $location.search('flavor', null);
        }

        return $rootScope.$broadcast('flavors:select', blueprint);
      };

      flavors.set = function(deployment) {
        var selected;

        if(!deployment.flavors) {
          this.reset();
          return;
        }

        this.original = angular.copy(deployment);
        this.data = angular.copy(deployment.flavors);
        this.list = angular.copy(_.map(this.data, function(flav, id) {
          return {
            'name': ((flav.blueprint || {})['meta-data'] || {}).flavor,
            'id': id,
            'weight': ((flav.blueprint || {})['meta-data'] || {})['flavor-weight']
          };
        }));

        this.list.push(this.default);

        if($route.current.params.flavor) {
          this.selected = $route.current.params.flavor;
        } else {
          this.selected = flavors.default.id;
        }

        return this.select();
      };

      return flavors;
    }
  ]);
