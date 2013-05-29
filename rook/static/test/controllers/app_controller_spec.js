describe('AppController', function(){
  var scope,
      http,
      location,
      resource,
      auth,
      $route,
      controller,
      api_stub;

  beforeEach(function(){
    scope = { $on: sinon.stub(), $root: {} };
    http = {};
    location = {};
    resource = function(){ return api_stub; };
    auth = {};
    $route = {};
    api_stub = { get: emptyFunction };
    controller = new AppController(scope, http, location, resource, auth, $route);
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

  describe('#impersonate', function() {
    var $rootScope, deferred;
    beforeEach(inject(function(_$rootScope_, $q) {
      $rootScope = _$rootScope_;
      deferred = $q.defer();
    }));

    it('should call the appropriate callback after impersonating user', function() {
      deferred.resolve('success');
      auth.impersonate = sinon.stub().returns(deferred.promise);
      scope.on_impersonate_success = sinon.stub();
      scope.impersonate('fakeuser');
      $rootScope.$apply();
      expect(scope.on_impersonate_success).toHaveBeenCalled();
    });

    it('should call the appropriate callback if unable to impersonate user', function() {
      deferred.reject('error');
      auth.impersonate = sinon.stub().returns(deferred.promise);
      scope.on_auth_failed = sinon.stub();
      scope.impersonate('fakeuser');
      $rootScope.$apply();
      expect(scope.on_auth_failed).toHaveBeenCalled();
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

    describe('when token is expired', function() {
      beforeEach(function() {
        auth.context.token.expires = "1970-01-01 0:00:00";
      });

      it('should reimpersonate the current tenant if impersonating', function() {
        auth.is_impersonating = sinon.stub().returns(true);
        var impersonation_callbacks = sinon.spy();
        scope.impersonate.andReturn( { then: impersonation_callbacks } );
        scope.check_token_validity();
        expect(scope.impersonate).toHaveBeenCalled();
        expect(impersonation_callbacks).toHaveBeenCalledWith(scope.on_impersonate_success, scope.on_auth_failed);
      });

      it('should display login prompt if not impersonating', function() {
        auth.is_impersonating = sinon.stub().returns(false);
        scope.check_token_validity();
        expect(auth.error_message).not.toBe(undefined);
        expect(scope.loginPrompt).toHaveBeenCalled();
      });
    });
  });
});
