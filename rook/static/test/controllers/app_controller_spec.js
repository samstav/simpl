describe('AppController', function(){
  var scope,
      http,
      location,
      resource,
      auth,
      $route,
      $q,
      webengage,
      controller,
      api_stub;

  beforeEach(function(){
    scope = { $on: sinon.stub(), $root: {} };
    http = {};
    location = {};
    resource = function(){ return api_stub; };
    auth = {};
    $route = {};
    $q = { defer: sinon.stub().returns( { promise: "fakepromise", reject: sinon.spy() } ) };
    api_stub = { get: emptyFunction };
    webengage = { init: emptyFunction };
    controller = new AppController(scope, http, location, resource, auth, $route, $q, webengage);
    mixpanel = { track: sinon.spy() }; // TODO: We are dependent on this being a global var
  });

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
      var response = {};
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
      expect(scope.open_modal).toHaveBeenCalledWith('error');
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
      expect(location.url).toHaveBeenCalledWith('/');
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
      auth.context = { token: {} }
      spyOn(scope, 'loginPrompt');
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
        auth.is_impersonating = sinon.stub().returns(true);
        var impersonation_callbacks = sinon.spy();
        scope.impersonate.andReturn( { then: impersonation_callbacks } );
        scope.check_token_validity();
        expect(scope.impersonate).toHaveBeenCalled();
        expect(impersonation_callbacks).toHaveBeenCalledWith(scope.on_impersonate_success, scope.on_auth_failed);
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

        it('should set force logout flag to true', function() {
          expect(scope.force_logout).toBe(true);
        });

        it('should bind #check_permissions to login modal box', function() {
          modalAuth.trigger('hide');
          expect(scope.$apply).toHaveBeenCalledWith(scope.check_permissions);
        });
      });
    });
  });

  describe('#check_permissions', function() {
    beforeEach(function() {
      spyOn(scope, 'logOut');
    });

    describe('if flag is true', function() {
      beforeEach(function() {
        scope.force_logout = true;
        scope.check_permissions();
      });

      it('should force user to log out', function() {
        expect(scope.logOut).toHaveBeenCalled();
      });

      it('should unset the flag', function() {
        expect(scope.force_logout).toBe(false);
      });

      it('should reset bound username', function() {
        expect(scope.bound_creds.username).toBe('');
      });
    });

    it('should do nothing if flag is not set or is set to false', function() {
      scope.force_logout = false;
      scope.check_permissions();
      expect(scope.logOut).not.toHaveBeenCalled();
    });
  });

  describe('#on_auth_success', function() {
    var deferred_login;
    beforeEach(function() {
      deferred_login = { resolve: sinon.spy() };
      scope.deferred_login = deferred_login;
      spyOn(scope, 'close_login_prompt');
      auth.identity = { username: "fakeusername" };
      $route.reload = sinon.spy();
      scope.on_auth_success();
    });

    it('should reset bound username', function() {
      expect(scope.bound_creds.username).toBeFalsy();
    });

    it('should reset bound password', function() {
      expect(scope.bound_creds.password).toBeFalsy();
    });

    it('should reset bound apikey', function() {
      expect(scope.bound_creds.apikey).toBeFalsy();
    });

    it('should clear auth error message', function() {
      expect(auth.error_message).toBeFalsy();
    });

    it('should resolve the deferred login promise', function() {
      expect(deferred_login.resolve).toHaveBeenCalledWith({ logged_in: true });
    });

    it('should erase the deferred login promise', function() {
      expect(scope.deferred_login).toBe(null);
    });

    it('should close the login prompt', function() {
      expect(scope.close_login_prompt).toHaveBeenCalled();
    });

    it('should reload current route', function() {
      expect($route.reload).toHaveBeenCalled();
    });
  });

  describe('#on_auth_failed', function() {
    beforeEach(function() {
      var response = { status: "fakestatustext" };
      scope.on_auth_failed(response);
    });

    it('should log response to mixpanel', function() {
      expect(mixpanel.track).toHaveBeenCalledWith('Log In Failed', { problem: "fakestatustext" });
    });

    it('should add an error message to auth service', function() {
      expect(auth.error_message).toEqual("fakestatustext. Check that you typed in the correct credentials.");
    });
  });

  describe('login_prompt_opts', function() {
    it('should set backdropFade to true', function() {
      expect(scope.login_prompt_opts.backdropFade).toBe(true);
    });

    it('should set dialogFade to true', function() {
      expect(scope.login_prompt_opts.dialogFade).toBe(true);
    });
  });

  describe('display_login_prompt', function() {
    it('should default to false', function() {
      expect(scope.display_login_prompt).toBe(false);
    });
  });

  describe('#loginPrompt', function() {
    var deferred_login_promise;
    beforeEach(function() {
      deferred_login_promise = scope.loginPrompt();
    });

    it('should set display_login_prompt to true', function() {
      expect(scope.display_login_prompt).toBe(true);
    });

    it('should return a deferred login promise', function() {
      expect(deferred_login_promise).toEqual("fakepromise");
    });
  });

  describe('#close_login_prompt', function() {
    it('should set display_login_prompt to false', function() {
      scope.close_login_prompt();
      expect(scope.display_login_prompt).toBe(false);
    });

    it('should reject the login promise if it has not been cleared', function() {
      scope.deferred_login = $q.defer();
      scope.close_login_prompt();
      expect(scope.deferred_login.reject).toHaveBeenCalledWith({ logged_in: false, reason: 'dismissed' });
    });
  });

  describe('#logIn', function() {
    beforeEach(function() {
      auth.authenticate = sinon.stub().returns({ then: emptyFunction });
      scope.get_selected_endpoint = sinon.stub().returns({ uri: "fakeendpoint" });
      scope.logIn();
    });

    it('should reset force_logout flag', function() {
      expect(scope.force_logout).toBe(false);
    });

    it('should call try to authenticate the user', function() {
      expect(auth.authenticate).toHaveBeenCalled();
    });
  });

  describe('#logOut', function() {
    beforeEach(function() {
      auth.logOut = sinon.spy();
      scope.logOut();
    });

    it('should clear auth error message', function() {
      expect(auth.error_message).toBeFalsy();
    });

    it('should call auth#logOut', function() {
      expect(auth.logOut).toHaveBeenCalled();
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

  describe('modal_window', function() {
    it('should default to empty object', function() {
      expect(scope.modal_window).toEqual({});
    });
  });

  describe('#open_modal', function() {
    it('should set modal flag to true', function() {
      scope.open_modal('fakemodal');
      expect(scope.modal_window.fakemodal).toBe(true);
    });
  });

  describe('#close_modal', function() {
    it('should set modal flag to false', function() {
      scope.close_modal('fakemodal');
      expect(scope.modal_window.fakemodal).toBe(false);
    });
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
      spyOn(angular, 'element').andReturn(entries_elements);
      scope.add_popover_listeners();
    });

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
      popover_element = { remove: sinon.spy(), siblings: sinon.stub().returns([{}]), scope: sinon.stub().returns(inner_scope) }
      spyOn(angular, 'element').andReturn(popover_element);
      scope.remove_popovers();
    });

    it('should remove .popover from DOM', function() {
      expect(popover_element.remove).toHaveBeenCalled();
    });

    it('should set tt_isOpen flags to false', function() {
      expect(inner_scope.tt_isOpen).toBe(false);
    });
  });
});
