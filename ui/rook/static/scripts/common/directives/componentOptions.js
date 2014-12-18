angular.module('checkmate.ComponentOptions', []);

angular.module('checkmate.ComponentOptions')
  .directive('componentOptions', function(Deployment, $compile, options) {
    return {
      restrict: 'EA',
      scope: {
        component: '=',
        options: '='
      },
      link: function(scope, element, attrs) {
        scope.templates = '/scripts/app/applications/options.tpl.html';
      },
      template: '<div><form name="BlueprintOptionForm"><cm-option ng-repeat="option in opts track by $index"/></cm-option><button ng-click="save()">Save</button></form></div><ng-include src="templates"></ng-include>',
      controller: function($scope, $element, $attrs) {
        $scope.$watch('options', function(newVal) {
          $scope.inputs = {};
          $scope.opts = [];

          _.each($scope.options, function(option, key) {
            option.id = key;
            $scope.opts.push(option);
          });
        });

        $scope.save = function() {
          console.log($scope.inputs);
        };
      }
    };
  });
