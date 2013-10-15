describe('AppController', function(){
  var scope,
      http,
      location,
      resource,
      auth,
      $route,
      $q,
      $modal,
      webengage,
      controller,
      api_stub;

  beforeEach(module('checkmate'));

  beforeEach(inject(function($injector) {
    scope = { $on: sinon.stub(), $root: {} };
    http = {};
    location = {};
    resource = function(){ return api_stub; };
    auth = $injector.get('auth');
    $route = {};
    $q = { defer: sinon.stub().returns( { promise: "fakepromise", reject: sinon.spy() } ) };
    $modal = $injector.get('$modal');
    api_stub = { get: emptyFunction };
    webengage = { init: emptyFunction };
    controller = new AppController(scope, http, location, resource, auth, $route, $q, webengage, $modal);
    mixpanel = { track: sinon.spy() }; // TODO: We are dependent on this being a global var
  }));

  it('should display the header', function(){
    expect(scope.showHeader).toBe(true);
  });

  it('should not display status', function(){
    expect(scope.showStatus).toBe(false);
  });

  describe('#select_endpoint', function() {
    var endpoint;
    beforeEach(function() {
      endpoint = { uri: 'fakeuri' };
      spyOn(localStorage, 'setItem');
    });

    it('should store current endpoint in auth service', function() {
      scope.select_endpoint(endpoint);
      expect(auth.selected_endpoint).toEqual({ uri: 'fakeuri' });
    });

    it('should store current endpoint in localStorage', function() {
      scope.select_endpoint(endpoint);
      expect(localStorage.setItem).toHaveBeenCalledWith('selected_endpoint', '{"uri":"fakeuri"}');
    });
  });

  describe('#get_selected_endpoint', function() {
    var endpoint;
    beforeEach(function() {
      endpoint = { uri: 'fakeuri' };
      endpoint_string = '{"uri":"fakeuri"}';
      auth.endpoints = [];
      spyOn(localStorage, 'getItem').andReturn(undefined);
      spyOn(JSON, 'parse');
    });

    it('should get selected endpoint from localStorage, if present', function() {
      localStorage.getItem.andReturn(endpoint_string);
      JSON.parse.andReturn(endpoint);
      expect(scope.get_selected_endpoint()).toEqual({ uri: 'fakeuri' });
    });

    it('should get selected endpoint from auth#selected_endpoint, if present', function() {
      auth.selected_endpoint = endpoint;
      expect(scope.get_selected_endpoint()).toEqual({ uri: 'fakeuri' });
    });

    it('should default to first endpoint if it has not been saved yet', function() {
      auth.endpoints = [endpoint, {}, {}]
      expect(scope.get_selected_endpoint()).toEqual({ uri: 'fakeuri' });
    });

    it('should default to an empty object if endpoints have not been loaded yet', function() {
      expect(scope.get_selected_endpoint()).toEqual({});
    });
  });

  describe('#realm_name', function() {
    it('should return a sanitized version of the endpoint realm', function() {
      var endpoint = { realm: 'fake realm 123!' };
      expect(scope.realm_name(endpoint)).toEqual('fakerealm123');
    });
  });

  describe('#display_announcement', function() {
    it('should display impersonation annuncement if Rackspace SSO has the highest priority', function() {
      auth.endpoints = [ { realm: "Rackspace SSO" }, {}, {} ];
      expect(scope.display_announcement()).toBe(true);
    });

    it('should not display impersonation annuncement if Rackspace SSO does not have the highest priority', function() {
      auth.endpoints = [ {}, { realm: "Rackspace SSO" }, {} ];
      expect(scope.display_announcement()).toBe(false);
    });

    it('should not display impersonation annuncement if endpoints are not defined', function() {
      auth.endpoints = [];
      expect(scope.display_announcement()).toBe(false);
    });
  });

  describe('#is_active', function() {
    beforeEach(function() {
      spyOn(scope, 'get_selected_endpoint').andReturn({ uri: 'fakeuri' });
    });

    it('should detect active endpoint if they have the same URI', function() {
      endpoint = { uri: 'fakeuri' };
      expect(scope.is_active(endpoint)).toEqual("active");
    });

    it('should detect inactive endpoint', function() {
      endpoint = { uri: 'anotherfakeuri' };
      expect(scope.is_active(endpoint)).toEqual("");
    });

    it('should detect inactive endpoint if endpoint is invalid', function() {
      endpoint = 1;
      expect(scope.is_active(endpoint)).toEqual("");
    });
  });

  describe('#is_hidden', function() {
    it('should hide GlobalAuthImpersonation from endopints', function() {
      endpoint = { scheme: "GlobalAuthImpersonation" };
      expect(scope.is_hidden(endpoint)).toBe(true);
    });

    it('should display all other endpoints', function() {
      endpoint = { scheme: 'fakescheme' };
      expect(scope.is_hidden(endpoint)).toBe(false);
    });
  });

  describe('#is_sso', function() {
    var endpoint;
    beforeEach(function() {
      endpoint = { uri: "fakeuri" };
    });

    it('should return true if endpoint is an SSO endpoint', function() {
      endpoint = { uri: "https://identity-internal.api.rackspacecloud.com/v2.0/tokens" };
      expect(scope.is_sso(endpoint)).toBe(true);
    });

    it('should return false if endpoint is not an SSO endpoint', function() {
      expect(scope.is_sso(endpoint)).toBe(false);
    });
  });

  describe('#impersonate', function() {
    var $rootScope, deferred;
    beforeEach(inject(function(_$rootScope_, $q) {
      $rootScope = _$rootScope_;
      deferred = $q.defer();
      auth.identity = { username: 'fakeracker' };
      auth.impersonate = sinon.stub().returns(deferred.promise);
      scope.on_impersonate_error = sinon.stub();
      scope.on_impersonate_success = sinon.stub();
      scope.impersonate('fakeuser');
    }));

    it('should log impersonation on mixpanel', function() {
      expect(mixpanel.track).toHaveBeenCalledWith('Impersonation', {user: 'fakeracker', tenant: 'fakeuser'});
    });

    it('should call the appropriate callback after impersonating user', function() {
      deferred.resolve('success');
      $rootScope.$apply();
      expect(scope.on_impersonate_success).toHaveBeenCalled();
    });

    it('should call the appropriate callback if unable to impersonate user', function() {
      deferred.reject('error');
      scope.impersonate('fakeuser');
      $rootScope.$apply();
      expect(scope.on_impersonate_error).toHaveBeenCalled();
    });
  });

  describe('#on_impersonate_success', function() {
    beforeEach(function() {
      auth.context = { tenantId: '666666' }
      $route.reload = sinon.stub();
      location.path = sinon.stub();
    });

    it('should redirect to new tenant path if under one', function() {
      location.path.returns('/555555/somepath');
      scope.on_impersonate_success();
      expect(location.path).toHaveBeenCalledWith('/666666/somepath');
    });

    it('should reload current anonymous path', function() {
      location.path.returns('/somepath');
      scope.on_impersonate_success();
      expect($route.reload).toHaveBeenCalled();
    });
  });

  describe('#on_impersonate_error', function() {
    beforeEach(function() {
      var response = {
        data: 'fake_data',
        status: 'fake_status'
      };
      scope.open_modal = sinon.spy();
      scope.on_impersonate_error(response);
    });

    it('should log error to mixpanel', function() {
      expect(mixpanel.track).toHaveBeenCalledWith('Impersonation Failed');
    });

    it('should set an error message', function() {
      expect(scope.$root.error).not.toBe(null);
    });

    it('should show an error modal', function() {
      var template = '/partials/app/_error.html';
      expect(scope.open_modal).toHaveBeenCalled('error');
      var call_template = scope.open_modal.getCall(0).args[0];
      var call_error = scope.open_modal.getCall(0).args[1];
      expect(call_template).toEqual(template)
      expect(call_error.error.data).toEqual('fake_data');
      expect(call_error.error.status).toEqual('fake_status');
    });
  });

  describe('#exit_impersonation', function() {
    beforeEach(function() {
      auth.exit_impersonation = sinon.spy();
      location.url = sinon.spy();
      scope.exit_impersonation();
    });

    it('should go back to admin context', function() {
      expect(auth.exit_impersonation).toHaveBeenCalled();
    });

    it('should redirect user to the homepage', function() {
      expect(location.url).toHaveBeenCalledWith('/admin/deployments');
    })
  });

  describe('#is_impersonating', function() {
    it('should call auth#is_impersonating', function() {
      auth.is_impersonating = sinon.spy();
      scope.is_impersonating();
      expect(auth.is_impersonating).toHaveBeenCalled();
    });
  });

  describe('#in_admin_context', function() {
    it('should not be in admin context if logged in as a tenant', function() {
      auth.identity = { is_admin: false };
      expect(scope.in_admin_context()).toBe(false);
    });

    it('should be in admin context if logged in as admin and not impersonating a tenant', function() {
      auth.identity = { is_admin: true };
      auth.is_impersonating = sinon.stub().returns(false);
      expect(scope.in_admin_context()).toBe(true);
    });

    it('should not be in admin context when impersonating a tenant', function() {
      auth.identity = { is_admin: true };
      auth.is_impersonating = sinon.stub().returns(true);
      expect(scope.in_admin_context()).toBe(false);
    });
  });

  describe('#check_token_validity', function() {
    beforeEach(function() {
      auth.context = { token: {} };
      spyOn(scope, 'loginPrompt').andReturn({ then: emptyFunction });
      spyOn(scope, 'impersonate');
    });

    it('should be added to $routeChangeStart watcher', function() {
      expect(scope.$on).toHaveBeenCalledWith('$routeChangeStart', scope.check_token_validity);
    });

    it('should do nothing if context token is still valid', function() {
      auth.context.token.expires = "9999-01-01 0:00:00";
      scope.check_token_validity();
      expect(scope.loginPrompt).not.toHaveBeenCalled();
      expect(scope.impersonate).not.toHaveBeenCalled();
    });

    it('should do nothing if token does not exist', function() {
      auth.context.token = null;
      scope.check_token_validity();
      expect(scope.loginPrompt).not.toHaveBeenCalled();
      expect(scope.impersonate).not.toHaveBeenCalled();
    });

    describe('when token is expired', function() {
      beforeEach(function() {
        auth.context.token.expires = "Thu Jan 01 1970 00:00:00";
      });

      it('should reimpersonate the current tenant if impersonating', function() {
        spyOn(auth, 'is_impersonating').andReturn(true);
        var impersonation_callbacks = sinon.spy();
        scope.impersonate.andReturn( { then: impersonation_callbacks } );
        scope.check_token_validity();
        expect(scope.impersonate).toHaveBeenCalled();
        expect(impersonation_callbacks).toHaveBeenCalledWith(scope.on_impersonate_success, scope.on_impersonate_error);
      });

      describe('if not impersonating', function() {
        var modalAuth;
        beforeEach(function() {
          auth.is_impersonating = sinon.stub().returns(false);
          auth.context.username = "fakeusername";
          spyOn($('#modalAuth'), 'one');
          scope.$apply = sinon.spy();
          modalAuth = $('<div id="modalAuth">');
          $(document.body).append(modalAuth);
          scope.check_token_validity();
        });
        afterEach(function() {
          modalAuth.remove();
          modalAuth = null;
        });

        it('should display login prompt', function() {
          expect(scope.loginPrompt).toHaveBeenCalled();
        });

        it('should set an error message', function() {
          expect(auth.error_message).not.toBe(undefined);
        });

        it('should bind username to login form', function() {
          expect(scope.bound_creds.username).not.toBeFalsy();
        });
      });
    });
  });

  describe('#loginPrompt', function() {
    var deferred_login_promise;
    beforeEach(function() {
      scope.open_modal = sinon.spy();
    });

    it('should open the login prompt partial with empty data', function() {
      var template = '/partials/app/login_prompt.html';
      scope.loginPrompt();
      expect(scope.open_modal).toHaveBeenCalledWith(template, {}, scope, LoginModalController);
    });
  });

  describe('modal_opts', function() {
    it('should set backdropFade to false', function() {
      expect(scope.modal_opts.backdropFade).toBe(false);
    });

    it('should set dialogFade to false', function() {
      expect(scope.modal_opts.dialogFade).toBe(false);
    });
  });

  describe('#open_modal', function() {
    beforeEach(function() {
      spyOn($modal, 'open');
    });

    it('should setup the template name', function() {
    });
    it('should setup the data for the modal', function() {});
    it('should pass in the given scope', function() {});
    it('should use the current scope if no scope is given', function() {});
    it('should pass in the given controller', function() {});
    it('should use ModalInstanceController if no controller is given', function() {});
    it('should open the modal window', function() {});
    it('should return a promise', function() {});
  });

  describe('hidden_alerts', function() {
    it('should default to empty object', function() {
      expect(scope.hidden_alerts).toEqual({});
    });
  });

  describe('#hide_alert', function() {
    it('should set hidden alert flag to true', function() {
      scope.hide_alert('fakealert');
      expect(scope.hidden_alerts.fakealert).toBe(true);
    });
  });

  describe('#display_alert', function() {
    it('should display alerts that have not been hidden', function() {
      expect(scope.display_alert('fakealert')).toBe(true);
    });

    it('should not display alerts that have explicitly been hidden', function() {
      scope.hidden_alerts.fakealert = true;
      expect(scope.display_alert('fakealert')).toBe(false);
    });
  });

  describe('#add_popover_listeners', function() {
    var entries_elements;
    beforeEach(function() {
      entries_elements = { on: sinon.spy() };
      sinon.stub(angular, 'element').returns(entries_elements)
      scope.add_popover_listeners();
    });

    afterEach(function(){
      angular.element.restore();
    })

    it('should add callback to scroll events on .entries', function() {
      expect(angular.element).toHaveBeenCalledWith('.entries');
      expect(entries_elements.on).toHaveBeenCalledWith('scroll');
    });

    it('should add remove_popovers to scroll event', function() {
      var anonymous = entries_elements.on.getCall(0).args[1];
      scope.$apply = sinon.spy();
      anonymous();
      expect(scope.$apply).toHaveBeenCalledWith(scope.remove_popovers);
    });

    it('should be added to $viewContentLoaded watcher', function() {
      expect(scope.$on).toHaveBeenCalledWith('$viewContentLoaded', scope.add_popover_listeners);
    });
  });

  describe('#remove_popovers', function() {
    var popover_element, inner_scope;
    beforeEach(function() {
      inner_scope = {tt_isOpen: "somevalue"};
      popover_element = { remove: sinon.spy(), siblings: sinon.stub().returns([{}]), scope: sinon.stub().returns(inner_scope) };
      sinon.stub(angular, 'element').returns(popover_element)
      scope.remove_popovers();
    });

    afterEach(function(){
      angular.element.restore();
    })

    it('should remove .popover from DOM', function() {
      expect(popover_element.remove).toHaveBeenCalled();
    });

    it('should set tt_isOpen flags to false', function() {
      expect(inner_scope.tt_isOpen).toBe(false);
    });
  });

  describe('#notify', function() {
    it('should have access to a default empty notification queue', function() {
      expect(scope.notifications).toEqual([]);
    });

    it('should push messages to notification queue', function() {
      scope.notify('fake message 1');
      scope.notify('fake message 2');
      scope.notify('fake message 3');
      expect(scope.notifications.length).toBe(3);
    });
  });

  describe('#wrap_admin_call', function() {
    var username, callback, arg1, arg2;
    beforeEach(function() {
      username = 'batman';
      callback = sinon.spy();
      arg1 = 'foo';
      arg2 = 'bar';
      auth.is_admin = sinon.stub().returns(false);
    });

    it('should test if user is strictly an admin', function() {
      scope.wrap_admin_call(username, callback, arg1, arg2);
      expect(auth.is_admin).toHaveBeenCalledWith(true);
    });

    it('should call callbacks with any number of parameters', function() {
      scope.wrap_admin_call(username, callback, arg1);
      expect(callback).toHaveBeenCalledWith(arg1);
      scope.wrap_admin_call(username, callback, arg1, arg2);
      expect(callback).toHaveBeenCalledWith(arg1, arg2);
    });

    it('should call callback with parameters if not an admin', function() {
      scope.wrap_admin_call(username, callback, arg1, arg2);
      expect(callback).toHaveBeenCalledWith(arg1, arg2);
    });

    it('should call callback with parameters if impersonating', function() {
      scope.wrap_admin_call(username, callback, arg1, arg2);
      expect(callback).toHaveBeenCalledWith(arg1, arg2);
    });

    describe('when admin', function() {
      var deferred, $rootScope;
      beforeEach(function() {
        angular.mock.inject(['$rootScope', '$q', function($rootScope_, $q_) {
          $rootScope = $rootScope_;
          $q = $q_;
        }]);
        deferred = $q.defer();
        auth.impersonate = sinon.stub().returns(deferred.promise);
        auth.is_admin.returns(true);
        scope.wrap_admin_call(username, callback, arg1, arg2);
      });

      it('should impersonate user', function() {
        expect(auth.impersonate).toHaveBeenCalled();
      });

      it('should not call callback yet', function() {
        expect(callback).not.toHaveBeenCalled();
      });

      describe('and promise gets resolved', function() {
        beforeEach(function() {
          auth.exit_impersonation = sinon.spy();
          deferred.resolve('impersonation worked!');
          $rootScope.$apply();
        });

        it('should call callback with parameters', function() {
          expect(callback).toHaveBeenCalledWith(arg1, arg2);
        });

        it('should exit impersonationg', function() {
          expect(auth.exit_impersonation).toHaveBeenCalled();
        });
      });
    });
  });
});
