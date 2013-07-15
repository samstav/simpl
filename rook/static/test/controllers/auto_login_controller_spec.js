describe('AutoLoginController', function(){
  var scope,
      location,
      cookies,
      auth,
      controller;

  beforeEach(function() {
    scope = { '$apply': emptyFunction, loginPrompt: emptyFunction };
    location = { path: emptyFunction };
    cookies = {};
    auth = {};
    controller = new AutoLoginController(scope, location, cookies, auth);
    mixpanel = { track: emptyFunction }; // TODO: We are dependent on this being a global var
  });

  it('should assign autologin callbacks and method to the scope', function(){
    expect(scope.auto_login_success).not.toBe(null);
    expect(scope.auto_login_fail).not.toBe(null);
    expect(scope.autoLogIn).not.toBe(null);
  });

  describe('auto_login_fail', function(){
    var response;

    beforeEach(function() {
      response = { status: 'faketext' };
    });

    it('should track the failure with mixpanel', function(){
      sinon.spy(mixpanel, 'track');
      scope.auto_login_fail(response);

      expect(mixpanel.track.getCall(0).args[0]).toEqual('Log In Failed');
      expect(mixpanel.track.getCall(0).args[1]).toEqual({ 'problem': 'faketext' });
    });

    it('should set the location path', function(){
      sinon.spy(location, 'path');
      scope.auto_login_fail(response);

      expect(location.path.getCall(0).args[0]).toEqual('/');
    });
  });

  describe('auto_login_success', function(){
    it('should set the location path', function(){
      sinon.spy(location, 'path');
      scope.auto_login_fail({ statusText: 'blah' });

      expect(location.path.getCall(0).args[0]).toEqual('/');
    });
  });

  describe('autoLogIn', function(){
    var promise_callback;
    beforeEach(function(){
      promise_callback = sinon.spy();
      auth.authenticate = sinon.stub().returns({ then: promise_callback });
      cookies.endpoint = 'www.uri.com';
      cookies.token = 'token';
      cookies.tenantId = 'tenantId';
      auth.endpoints = [{ uri: 'www.uri.com', scheme: 'Kablamo' }];
    });

    it('should call authenticate with the matching endpoint', function(){
      scope.autoLogIn();

      expect(auth.authenticate.getCall(0).args[0]).toEqual({ uri: 'www.uri.com', scheme: 'Kablamo' });
    });

    it('should pass an empty endpoint object if no matches are found', function(){
      auth.endpoints = [];
      scope.autoLogIn();

      expect(auth.authenticate.getCall(0).args[0]).toEqual({});
    });

    it('should call authenticate with token/tenantId', function(){
      scope.autoLogIn();

      expect(auth.authenticate.getCall(0).args[0]).toEqual(auth.endpoints[0]);
      expect(auth.authenticate.getCall(0).args[4]).toEqual('token');
      expect(auth.authenticate.getCall(0).args[6]).toEqual('tenantId');
    });

    it('should call authenticate with username/api_key', function(){
      delete cookies.token;
      delete cookies.tenantId;
      cookies.username = 'batman';
      cookies.api_key = 'secret key';
      scope.autoLogIn();

      expect(auth.authenticate.getCall(0).args[0]).toEqual(auth.endpoints[0]);
      expect(auth.authenticate.getCall(0).args[1]).toEqual('batman');
      expect(auth.authenticate.getCall(0).args[2]).toEqual('secret key');
    });

    it('should pass success and error callbacks', function() {
      scope.autoLogIn();
      expect(promise_callback).toHaveBeenCalledWith(scope.auto_login_success, scope.auto_login_fail);
    });
  });
});

