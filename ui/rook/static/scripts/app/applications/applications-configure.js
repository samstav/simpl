angular.module('checkmate.applications-configure', [
  'lvl.directives.dragdrop',
  'checkmate.Blueprint',
  'checkmate.Catalog',
  'checkmate.DeploymentData',
  'checkmate.Drag',
  'checkmate.ComponentOptions'
]);

angular.module('checkmate.applications-configure')
  .controller('ConfigureCtrl', function($scope, DeploymentData, Blueprint, Catalog, options, Drag, $timeout, $location, $resource) {

    $scope.deployment = DeploymentData.get();

    // This selects the object being sent to the Blueprint.
    $scope.select = function(app) {
      Drag.source.set(app);
    };

    // This triggers when something is dropped on the drop target.
    $scope.add = function() {
      var source = Drag.source.get();
      var target = Drag.target.get();

      Blueprint.add(source, target);
      Drag.reset();
    };

    // This could toggle an extra sidebar to reveal details about a service.
    $scope.selection = {
      data: {
        service: '',
        component: {},
        relation: null
      },
      isVisible: false,
      hasSelection: function() {
        return Blueprint.componentInService($scope.selection.data.component, $scope.selection.data.service);
      },
      open: function() {
        this.isVisible = true;
      },
      close: function() {
        this.isVisible = false;
      },
      parseOptions: function() {
        var workflow = {};
        var bp = $.extend({}, $scope.deployment.blueprint, $scope.catalog.components[$scope.selection.data.component]);
        //console.log(bp);
        //DeploymentNewController($scope, $location, $resource, options, workflow, bp, $scope.deployment.environment);
      }
    };

    // This is the catalog model for the sidebar.
    $scope.catalog = {
      isVisible: true,
      data: Catalog.get(),
      components: Catalog.getComponents(),
      component: function(component) {
        return Catalog.getComponent(component);
      }
    };

    $scope.$on('catalog:update', function(event, data) {
      $scope.catalog.data = Catalog.get();
      $scope.catalog.components = Catalog.getComponents();
    });

    // This is the codemirror model for the sidebar.
    $scope.codemirror = {
    };

    $scope.$on('deployment:update', function(event, data) {
      if(data.blueprint && _.size(data.blueprint.services) === 1) {
        $timeout(function() {
          $scope.codemirror.isVisible = true;
        }, 50);
      }

      $scope.deployment = data;
    });

    // Removes annotations, forces 'components' array to single 'component'
    $scope.prepDeployment = function(newFormatDeployment) {
      var deployment = angular.copy(newFormatDeployment);
      var blueprint = deployment.blueprint;
      var services = blueprint.services;
      _.each(services, function(value, key) {
        var components = value.components;
        var component;
        if (angular.isArray(components)) {
          component = components[0];
        } else {
          component = components;
        }
        delete value.components;
        if (angular.isString(component)) {
          component = {id: component};
        }
        value.component = component;
        delete value.annotations;
      });
      return deployment;
    };

    $scope.submit = function(action){
      if ($scope.submitting === true)
        return;
      $scope.submitting = true;

      var url = '/:tenantId/deployments';
      if (action)
        url += '/' + action;

      var Dep = $resource((checkmate_server_base || '') + url, {tenantId: $scope.auth.context.tenantId});
      var deployment = new Dep($scope.prepDeployment($scope.deployment));

      deployment.$save(
        function success(returned, getHeaders){
          if (action == '+preview') {
            workflow.preview = returned;
            $location.path('/' + $scope.auth.context.tenantId + '/workflows/+preview');
          } else {
            var deploymentId = getHeaders('location').split('/')[3];
            console.log("Posted deployment", deploymentId);
            $location.path(getHeaders('location'));
          }
        },
        function error(err) {
          $scope.show_error(err);
          $scope.submitting = false;
        }
      );
    };

    $scope.reset = function() {
      Blueprint.reset();
    };

    $scope.$on('topology:select', function(event, selection) {
      if (selection) {
        $scope.selection.data = selection;
        $scope.selection.parseOptions();
        $scope.selection.open();
      } else {
        $scope.selection.close();
        $scope.$apply();
      }
    });

    $scope.$on('topology:deselect', function(event, selection) {
      $scope.selection.close();
    });

  });
