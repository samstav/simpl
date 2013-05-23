describe('AppController', function(){
  var scope,
      http,
      location,
      resource,
      auth,
      controller,
      api_stub;

  beforeEach(function(){
    scope = { $on: sinon.stub(), $root: {} };
    http = {};
    location = {};
    resource = function(){ return api_stub; };
    auth = {};
    api_stub = { get: emptyFunction };
    controller = new AppController(scope, http, location, resource, auth);
  });

  it('should display the header', function(){
    expect(scope.showHeader).toBe(true);
  });

  it('should not display status', function(){
    expect(scope.showStatus).toBe(false);
  });

  it('should set auth#selected_endpoing', function() {
    endpoint = { uri: 'fakeuri' };
    scope.select_endpoint(endpoint);
    expect(auth.selected_endpoint).toEqual({ uri: 'fakeuri' });
  });

  it('should get selected endpoing', function() {
    endpoint = { uri: 'fakeuri' };
    scope.select_endpoint(endpoint);
    expect(scope.get_selected_endpoint()).toEqual({ uri: 'fakeuri' });
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
    it('should redirect to new tenant path if under one', function() {
      location.path = sinon.stub().returns('/555555/somepath');
      auth.context = { tenantId: '666666' }
      scope.on_impersonate_success();
      expect(location.path).toHaveBeenCalledWith('/666666/somepath');
    });

    it('should reload current anonymous path', function() {
      location.path = sinon.stub().returns('/somepath');
      auth.context = { tenantId: '666666' }
      scope.on_impersonate_success();
      expect(location.path).toHaveBeenCalledWith('/somepath');
    });
  });

});
