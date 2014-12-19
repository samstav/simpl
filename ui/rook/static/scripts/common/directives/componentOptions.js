angular.module('checkmate.ComponentOptions', []);

angular.module('checkmate.ComponentOptions')
  .directive('componentOptions', function(Blueprint, $compile, options) {
    return {
      restrict: 'EA',
      scope: {
        serviceId: '=',
        component: '=',
        options: '='
      },
      link: function(scope, element, attrs) {
        scope.templates = '/scripts/app/applications/options.tpl.html';
      },
      template: '<div> \
                    <form name="BlueprintOptionForm"> \
                      <cm-option ng-repeat="option in opts track by option.id"/></cm-option> \
                      <button class="rs-btn rs-btn-secondary" ng-click="save()">Save</button> \
                    </form> \
                  </div> \
                  <ng-include src="templates"></ng-include>',
      controller: function($scope, $element, $attrs) {
        $scope.inputs = {};
        $scope.opts = [];

        $scope.$watch('component', function(newVal) {
          $scope.inputs = {};
          $scope.opts = [];
          $scope.BlueprintOptionForm.$setPristine();
        }, true);

        $scope.$watch('options', function(newVal) {
          $scope.BlueprintOptionForm.$setPristine();
          var _opts = [];

          if($scope.component && $scope.serviceId) {
            var _constraints = angular.copy(Blueprint.getComponentConstraints($scope.serviceId, $scope.component.id || ''));
            var _inputs = {};

            _.each(_constraints, function(constraint, index) {
              // Assign input ids if 'setting' attr exists
              if(constraint.setting) {
                _inputs[constraint.setting] = constraint.value;
              }

              // Assign input ids if they're an available option.
              _.each($scope.options, function(option, id) {
                if(id in constraint) {
                  _inputs[id] = constraint[id];
                }
              });
            });

            $scope.inputs = _inputs;

            _.each(newVal, function(option, key) {
              option.id = key;
              _opts.push(option);
            });

            $scope.opts = _opts;
          }
        });

        $scope.save = function() {
          var _constraints = Blueprint.getComponentConstraints($scope.serviceId, $scope.component.id || '');
          var data = {
            serviceId: $scope.serviceId,
            component: $scope.component,
            constraints: []
          };

          // Loop over the payload data to convert back to an array.
          _.each($scope.inputs, function(input, id) {
            var newConstraint = {};
            var _exists = false;

            newConstraint[id] = input;

            // Rewrite the constraits without losing meta data.
            _.each(_constraints, function(constraint, index) {
              _exists = true;

              if(!id in constraint && !constraint.setting == id) {
                constraint[id] = input;
              }

              if(id in constraint) {
                constraint[id] = input;
              }

              if(constraint.setting == id) {
                constraint.value = input;
              }
            });

            if(!_exists) {
              _constraints.push(newConstraint);
            }
          });

          data.constraints = _constraints

          Blueprint.saveComponentConstraints(data);
        };
      }
    };
  });
