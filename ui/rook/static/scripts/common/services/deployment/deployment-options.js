angular.module('checkmate.DeploymentOptions', []);

angular.module('checkmate.DeploymentOptions')
  .directive('deploymentOptions', function($rootScope, DeploymentData, Blueprint) {
    return {
      restrict: 'EA',
      scope: {},
      templateUrl: '/partials/app/deployment_options.tpl.html',
      link: function() {

      },
      controller: function($scope) {
        populate();

        $scope.form = {
          message: {
            type: null,
            message: null
          }
        };

        $scope.providers = {
          hasExistingCreds: function() {
            return this.selected.templateUrl;
          },
          remove: function(provider) {
            var confirmRemove = confirm('Are you sure you want to remove this provider?');

            if(!confirmRemove) return;

            delete $scope.deployment.environment.providers[provider];
          },
          hasNoProviders: function() {
            return _.keys($scope.deployment.environment.providers).length > 0;
          }
        };

        $scope.save = function() {
          DeploymentData.set($scope.deployment);
          $scope.$parent.notify('Nice one! You updated the deployment.');
        };

        $scope.close = function() {
          $rootScope.$broadcast('deployment:toggle_options');
        };

        $scope.$on('deployment:toggle_options', function(selection) {
          populate();
        });

        function populate() {
          $scope.deployment = angular.copy(DeploymentData.get());
          $scope.deployment.blueprint = angular.copy(Blueprint.get());
        }
      }
    }
  });
