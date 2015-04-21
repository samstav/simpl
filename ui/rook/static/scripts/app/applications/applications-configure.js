angular.module('checkmate.applications-configure', [
  'lvl.directives.dragdrop',
  'checkmate.Blueprint',
  'checkmate.Catalog',
  'checkmate.Flavors',
  'checkmate.DeploymentData',
  'checkmate.Drag',
  'checkmate.ComponentOptions',
  'ngDialog'
]);

angular.module('checkmate.applications-configure')
  .controller('ConfigureCtrl', function($scope, DeploymentData, Blueprint, Catalog, options, Drag, $timeout, $location, $resource, deployment, github, $window, Flavors, ngDialog) {
    $scope.deployment = DeploymentData.get();

    $scope.export = function() {
      DeploymentData.export();
    };

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

    $scope.flavors = Flavors;

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
      get: Catalog.get,
      components: Catalog.getComponents(),
      component: function(component) {
        return Catalog.getComponent(component);
      },
      isLoading: Catalog.isLoading,
      hasError: Catalog.hasError
    };

    // This is the codemirror model for the sidebar.
    $scope.codemirror = {
      isFocused: false,
      hasError: false
    };

    $scope.controls = {
      canRevert: false
    };

    $scope.prompts = {
      codemirror: {
        message: 'Something is wrong with your Blueprint. You should fix the code in the editor or you can revert to when it last worked.',
        classes: ['rs-app-warning', 'revert-warning'],
        icon: 'fa fa-exclamation-triangle',
        isDismissible: false,
        isVisible: false,
        action: function() {
          $scope.revert();
        },
        actionLabel: 'Revert Blueprint'
      },
      githubEmptyRepo: {
        message: 'Yo, we couldn\'t find a valid Checkmate blueprint in this Github repo.',
        classes: ['rs-app-warning', 'github-empty-repo'],
        icon: 'fa fa-github',
        isDismissible: false,
        isVisible: false,
        action: function() {
          $location.url('/blueprints/design');
        },
        actionLabel: 'Dismiss'
      },
      githubInvalidImport: {
        message: 'We found a Checkmate blueprint in this repo but it\'s an invalid schema. We couldn\'t import it. :(',
        classes: ['rs-app-warning', 'github-invalid-import'],
        icon: 'fa fa-github',
        isDismissible: false,
        isVisible: false,
        action: function() {
          $location.url('/blueprints/design');
        },
        actionLabel: 'Dismiss'
      },
      githubAuth: {
        message: 'Is this a private repo? You should authenticate with your Github account.',
        classes: ['rs-app-processing', 'github-auth'],
        icon: 'fa fa-github',
        isDismissible: true,
        isVisible: false,
        action: function() {
          github.go_auth();
        },
        actionLabel: 'Connect Github'
      }
    };

    // Removes annotations, forces 'components' array to single 'component'
    $scope.prepDeployment = function(newFormatDeployment) {
      var deployment = angular.copy(newFormatDeployment);
      var blueprint = deployment.blueprint;
      var services = blueprint.services;

      // Move the deployment ID to the blueprint on deploy.
      if(deployment.id) {
        blueprint.id = deployment.id;
        delete deployment.id;
      }

      _.each(services, function(value, key) {
        var components = value.components;
        var component;

        if(angular.isArray(components)) {
          component = components[0];
        } else {
          component = components;
        }

        if(angular.isString(component)) {
          component = {id: component};
        }

        value.component = component;

        delete value.components;
        delete value.annotations;
      });

      return deployment;
    };

    $scope.save = function() {
      if($scope.deployment.id) {
        var save = ngDialog.openConfirm({
          template: 'dialog-save-and-overwrite-blueprint'
        });

        save.then(function (data) {
          $scope.$broadcast('blueprint:save', data);
        });
      } else {
        $scope.$broadcast('blueprint:save');
      }
    };

    $scope.submit = function(action) {
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
            if(!action) redirectUri();
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
        $scope.prompts.githubAuth.isVisible = true;
      } else if (!deployment && github.config.accessToken) {
        $scope.prompts.githubEmptyRepo.isVisible = true;
      } else {
        if(!DeploymentData.isValid(deployment)) {
          $scope.prompts.githubInvalidImport.isVisible = true;
        } else {
          $timeout(function(){
            DeploymentData.set(deployment);
          }, 50);
        }
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

    $scope.$on('blueprint:save', function(event, data) {
      var deployment = $scope.prepDeployment($scope.deployment);
      var overwrite = (data === 'UPDATE');

      DeploymentData.save($scope.auth.context.tenantId, deployment, overwrite);
    });

    $scope.$on('topology:error', function(event, data) {
      blockUi();
    });

    $scope.$on('editor:focus', function(event, data) {
      $scope.codemirror.isFocused = true;
    });

    $scope.$on('editor:blur', function(event, data) {
      $scope.codemirror.isFocused = false;
      if($scope.codemirror.isOutOfSync) blockUi();
    });

    $scope.$on('editor:out_of_sync', function(event, data) {
      $scope.codemirror.isOutOfSync = true;
    });

    $scope.$on('editor:nsync', function(event, data) {
      $scope.codemirror.isOutOfSync = false;
    });

    $scope.$on('flavors:select', function(event, blueprint) {
      Blueprint.set(blueprint);
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

    Catalog.load();

    function prepareUiBlock() {
      $scope.codemirror.isOutOfSync = true;
      $scope.controls.canRevert = true;
    }

    function blockUi() {
      if(!$scope.codemirror.isFocused) {
        $scope.codemirror.hasError = true;
        $scope.prompts.codemirror.isVisible = true;
      }
    }

    function unblockUi() {
      $scope.controls.canRevert = false;
      $scope.codemirror.isOutOfSync = false;
      $scope.codemirror.hasError = false;
      $scope.prompts.codemirror.isVisible = false;
    }
  });
