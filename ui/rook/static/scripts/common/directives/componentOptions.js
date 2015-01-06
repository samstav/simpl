angular.module('checkmate.ComponentOptions', []);

angular.module('checkmate.ComponentOptions')
.directive('registerInput', function($timeout, $parse) {
  return {
    restrict: 'A',
    link: function(scope, element, attr) {
      $timeout(function () {
        var inputs = element.find('input');
        var checkboxes = element.find('checkbox');
        var selects = element.find('select');
        var assign = function(target) {
          var name = angular.element(target).attr('ng-model');
          var model = $parse(name);

          if(!angular.isDefined(model(scope))) {
            model.assign(scope, null);
          }
        };

        _.each(inputs, function(input) {
          assign(input);
        });

        _.each(checkboxes, function(checkbox) {
          assign(checkbox);
        });

        _.each(selects, function(select) {
          assign(select);
        });
      });
    }
  };
});

angular.module('checkmate.ComponentOptions')
  .directive('componentOptions', function(Blueprint, $compile, options, $location, $route, $routeParams, $resource, DeploymentData, auth, $modal) {
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
      template: '<div class="component-editor"> \
                  <form name="BlueprintOptionForm"> \
                    <div class="rs-table-overlay" \
                         style="padding: 0 50px; width: auto; height: 200px;" \
                         ng-show="!opts.length"> \
                      <div class="rs-table-overlay-content"> \
                        <div class="rs-table-overlay-subtitle"> \
                          This component does not have any constraints to modify. \
                        </div> \
                      </div> \
                    </div> \
                    <cm-option ng-repeat="option in opts track by option.id" register-input /></cm-option> \
                  </form> \
                </div> \
                <div class="component-controls">\
                  <button ng-show="opts.length" \
                          class="rs-btn rs-btn-secondary" \
                          ng-click="save()"> \
                    Save Component Options \
                  </button> \
                </div>\
                <ng-include src="templates"></ng-include>',
      controller: function($scope, $element, $attrs) {
        $scope.inputs = {};
        $scope.opts = [];

        // Imported and dependent variables
        $scope.auth = auth;
        $scope.deployment = DeploymentData.get();
        $scope.domain_names = [];
        $scope.bound_creds = {
          username: '',
          password: '',
          apikey: ''
        };

        // START: These are functions from app.js that are not available in this scope.
        $scope.environment = $scope.deployment.environment;

        $scope.getDomains = function() {
          $scope.domain_names = [];
          var tenant_id = $scope.auth.context.tenantId;
          if ($scope.auth.identity.loggedIn && tenant_id){
            var url = '/:tenantId/providers/rackspace.dns/resources';
            var Domains = $resource((checkmate_server_base || '') + url, {tenantId: $scope.auth.context.tenantId});
            var results = Domains.query(function() {
              for(var i=0; i<results.length; i++){
                $scope.domain_names.push(results[i].name);
              }
            },
            function(response) {
              if (!('data' in response))
                response.data = {};
                response.data.description = "Error loading domain list";
              }
            );
          }
        };

        $scope.updateRegions = function() {
          if ($scope.environment) {
            if ('providers' in $scope.environment && 'legacy' in $scope.environment.providers) {
              if ($scope.options && $scope.auth.identity.loggedIn === true && 'RAX-AUTH:defaultRegion' in $scope.auth.context.user) {
                _.each($scope.options, function(option) {
                  if (option.id == 'region') {
                    option['default'] = $scope.auth.context.user['RAX-AUTH:defaultRegion'];
                    option.choice = [option['default']];
                    $scope.inputs[option.id] = option['default'];
                    option.description = "Your legacy cloud servers region is '" + option['default'] + "'. You can only deploy to this region";
                  }
                });
              }
            } else {
              _.each($scope.options, function(option) {
                if (option.id == 'region' && $scope.auth.identity.loggedIn === true) {
                  option.choice = $scope.auth.context.regions;
                  option.description = "";
                }
              });
            }
          }
        };

        $scope.OnAddressEditorShow = function() {
          site_address.value = calculated_site_address.innerText;
        };

        $scope.UpdateSiteAddress = function(new_address) {
          var parsed = URI.parse(new_address);
          if (!('hostname' in parsed)) {
            $('#site_address_error').text("Domain name or IP address missing");
            return;
          }
          if (!('protocol' in parsed)){
            $('#site_address_error').text("Protocol (http or https) is missing");
            return;
          }
          $('#site_address_error').text("");
          $scope.inputs['web_server_protocol'] = parsed.protocol;
          $scope.inputs['domain'] = parsed.hostname;
          $scope.inputs['path'] = parsed.path || "/";
        };

        $scope.UpdateURLOption = function(scope, option_id) {
          if ($scope.AcceptsSSLCertificate(scope) === true) {
            $scope.inputs[option_id] = {
              url: scope.url,
              certificate: scope.certificate,
              private_key: scope.private_key,
              intermediate_key: scope.intermediate_key
            };
          } else {
            $scope.inputs[option_id] = scope.url;
          }
        };

        $scope.UpdateURL = function(scope, option_id) {
          if(!scope.protocol) {
            return false;
          }
          var new_address = scope.protocol + '://' + scope.domain + scope.path;
          var parsed = URI.parse(new_address);
          scope.url = new_address;
          $scope.UpdateURLOption(scope, option_id);
        };

        $scope.UpdateParts = function(scope, option_id) {
          var input = scope.url || $scope.inputs[option_id];
          var address = input.url || input;
          var parsed = URI.parse(address);
          scope.protocol = parsed.protocol;
          scope.domain = parsed.hostname;
          scope.path = parsed.path;
        };

        $scope.AcceptsSSLCertificate = function(scope) {
          if ((scope.option['encrypted-protocols'] || []).indexOf(scope.protocol) > -1)
            return true;
            if (scope.option['always-accept-certificates'] === true)
              return true;
              return false;
            };

        $scope.ShowCerts = function() {
          if ('web_server_protocol' in $scope.inputs && $scope.inputs['web_server_protocol'].indexOf('https') != -1)
            return true;

          if ($scope.inputs.url && $scope.inputs['url'].indexOf('https') != -1)
            return true;

          return false;
        };

        $scope.showOptions = function() {
          return ($scope.environment && $scope.blueprint);
        };

        $scope.generatePassword = function() {
          if (parseInt(navigator.appVersion, 10) <= 3) {
            $scope.notify("Sorry this only works in 4.0+ browsers");
            return true;
          }

          var length = 10;
          var sPassword = "";

          var noPunction = true;
          for (i=0; i < length; i++) {
            var numI = $scope.getPwdRandomNum();
            //Always have a letter for the first character.
            while (i===0 && (numI <= 64 || ((numI >=91) && (numI <=96)))) {
              numI = $scope.getPwdRandomNum();
            }
            //Only allow letters and numbers for all other characters.
            while (((numI >=58) && (numI <=64)) || ((numI >=91) && (numI <=96))) {
              numI = $scope.getPwdRandomNum();
            }

            sPassword = sPassword + String.fromCharCode(numI);
          }

          return sPassword;
        };

        $scope.getPwdRandomNum = function() {
          // between 0 - 1
          var rndNum = Math.random();

          // rndNum from 0 - 1000
          rndNum = parseInt(rndNum * 1000, 10);

          // rndNum from 33 - 127
          rndNum = (rndNum % 75) + 48;

          return rndNum;
        };

        $scope.loginPrompt = function() {
          var data = {};
          var login_template = '/partials/app/login_prompt.html';
          return $scope.open_modal(login_template, data, $scope, LoginModalController);
        };

        $scope.open_modal = function(template_name, data, scope, controller) {
          var config = {
            templateUrl: template_name,
            controller: controller || ModalInstanceController,
            scope: scope || $scope,
            resolve: {
              data: function() {
                return data || {};
              }
            }
          };
          var modal_instance = $modal.open(config);
          return modal_instance.result;
        };

        $scope.display_announcement = function() {
          return (auth.endpoints[0] !== undefined) && (auth.endpoints[0].realm == "Rackspace SSO");
        };

        $scope.select_endpoint = function(endpoint) {
          auth.selected_endpoint = endpoint;
          localStorage.setItem('selected_endpoint', JSON.stringify(endpoint));
        };

        $scope.is_active = function(endpoint) {
          if ($scope.get_selected_endpoint().uri == endpoint.uri)
            return "active";
            return "";
        };

        $scope.realm_name = function(endpoint) {
          return endpoint.realm.toLowerCase().replace(/[^a-z0-9]/g, '');
        };

        $scope.is_hidden = function(endpoint) {
          return (endpoint.scheme == 'GlobalAuthImpersonation');
        };

        $scope.get_selected_endpoint = function() {
          var local_endpoint = localStorage.selected_endpoint || null;
          return JSON.parse(local_endpoint) || auth.selected_endpoint || auth.endpoints[0] || {};
        };

        $scope.uses_pin_rsa = function(endpoint) {
          return ($scope.get_selected_endpoint().scheme == "GlobalAuth");
        };

        $scope.is_sso = function(endpoint) {
          return endpoint.uri == 'https://identity-internal.api.rackspacecloud.com/v2.0/tokens';
        };
        // END: These were functions from app.js that are not available in this scope.

        $scope.$watch('component', function(newVal, oldVal) {
          $scope.inputs = {};
          $scope.opts = [];
          $scope.BlueprintOptionForm.$setPristine();
        }, true);

        $scope.$watch('options', function(newVal, oldVal) {
          $scope.BlueprintOptionForm.$setPristine();
          var _opts = [];

          if($scope.component && $scope.serviceId) {
            var _constraints = angular.copy(Blueprint.getComponentConstraints($scope.serviceId, ($scope.component.id || $scope.component.name || '')));
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

            _.each(newVal, function(option, key) {
              if(!_inputs[key])
                _inputs[key] = '';

              option.id = key;
              _opts.push(option);
            });

            $scope.inputs = _inputs;
            $scope.opts = _opts;
          }
        });

        $scope.save = function() {
          var id = ($scope.component.id || $scope.component.name || '');
          var _constraints = Blueprint.getComponentConstraints($scope.serviceId, id);
          var data = {
            serviceId: $scope.serviceId,
            component: $scope.component,
            constraints: []
          };

          // Loop over the payload data to convert back to an array.
          _.each($scope.inputs, function(input, id) {
            if(input == null || input.length < 1) {
              return;
            }

            var newConstraint = {};
            var _exists = false;

            newConstraint[id] = input;

            // Rewrite the constraits without losing meta data.
            _.each(_constraints, function(constraint, index) {
              if(id in constraint) {
                _exists = true;
                constraint[id] = input;
              }

              if(constraint.setting == id) {
                _exists = true;
                constraint.value = input;
              }
            });

            if(!_exists) {
              _constraints.push(newConstraint);
            }
          });

          data.constraints = _constraints;

          Blueprint.saveComponentConstraints(data);
        };
      }
    };
  });
