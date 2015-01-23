angular.module('checkmate.applications-configure', [
  'lvl.directives.dragdrop',
  'checkmate.Blueprint',
  'checkmate.Catalog',
  'checkmate.DeploymentData',
  'checkmate.Drag',
  'checkmate.ComponentOptions'
]);

angular.module('checkmate.applications-configure')
  .controller('ConfigureCtrl', function($scope, DeploymentData, Blueprint, Catalog, options, Drag, $timeout, $location, $resource, deployment, github, $window) {

    $scope.deployment = DeploymentData.get();

    // This selects the object being sent to the Blueprint.
    $scope.select = function(app) {
      Drag.source.set(app);
    };

    // This triggers when something is dropped on the drop target.
    $scope.add = function(source, target) {
      source = source || Drag.source.get();
      target = target || Drag.target.get();

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

    // This is the codemirror model for the sidebar.
    $scope.codemirror = {
      hasError: false
    };

    $scope.controls = {
      canRevert: false
    };

    $scope.prompts = {
      emptyRepo: {
        isVisible: false,
        action: function() {
          $location.url('/blueprints/design');
        }
      },
      github: {
        isVisible: false,
        action: function() {
          var url = [];
          var redirect_uri = [];

          redirect_uri.push($location.protocol());
          redirect_uri.push('://');
          redirect_uri.push($location.host());
          if($location.port() && $location.port() !== 80)
            redirect_uri.push(':'+$location.port());
          redirect_uri.push('/webhooks/github_auth');
          redirect_uri.push($location.path());

          url.push('https://github.com/login/oauth/authorize');
          url.push('?');
          url.push('scope=user:email,repo');
          url.push('&client_id='+$scope.$root.clientId);
          url.push('&redirect_uri='+redirect_uri.join(''));

          $window.location.href = url.join('');
        }
      }
    };

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
      DeploymentData.reset();
    };

    $scope.revert = function() {
      Blueprint.revert();
    };

    // If there's a deployment object resolved, let's use it.
    if(!_.isUndefined(deployment)) {
      DeploymentData.reset();

      if(!deployment && !github.config.accessToken && $scope.$root.clientId) {
        $scope.prompts.github.isVisible = true;
      } else if (!deployment && github.config.accessToken) {
        $scope.prompts.emptyRepo.isVisible = true;
      } else {
        $timeout(function(){
          DeploymentData.set(deployment);
        }, 50);
      }
    }

    $scope.$on('catalog:update', function(event, data) {
      $scope.catalog.data = Catalog.get();
      $scope.catalog.components = Catalog.getComponents();
    });

    $scope.$on('deployment:update', function(event, data) {
      if(data.blueprint && _.size(data.blueprint.services) > 0) {
        $timeout(function() {
          $scope.codemirror.isVisible = true;
        }, 50);
      }

      $scope.deployment = data;
    });

    $scope.$on('deployment:invalid', function(event, data) {
      prepareUiBlock();
    });

    $scope.$on('deployment:valid', function(event, data) {
      unblockUi();
    });

    $scope.$on('blueprint:invalid', function(event, data) {
      prepareUiBlock();
    });

    $scope.$on('blueprint:valid', function(event, data) {
      unblockUi();
    });

    $scope.$on('topology:error', function(event, data) {
      blockUi();
    });

    $scope.$on('editor:focus', function(event, data) {});

    $scope.$on('editor:blur', function(event, data) {
      if($scope.codemirror.isOutOfSync) blockUi();
    });

    $scope.$on('editor:out_of_sync', function(event, data) {
      $scope.codemirror.isOutOfSync = true;
    });

    $scope.$on('editor:nsync', function(event, data) {
      $scope.codemirror.isOutOfSync = false;
    });

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

    function prepareUiBlock() {
      $scope.codemirror.isOutOfSync = true;
      $scope.controls.canRevert = true;
    }

    function blockUi() {
      $scope.codemirror.hasError = true;
      $scope.$apply();
    }

    function unblockUi() {
      $scope.controls.canRevert = false;
      $scope.codemirror.isOutOfSync = false;
      $scope.codemirror.hasError = false;
    }
  });
