describe('controllers', function() {
  describe('AutoLoginController', function(){
    var scope, location, cookies, auth, controller;
    beforeEach(function() {
      scope = { '$apply': function(){}, loginPrompt: function(){} };
      location = { path: function(){} };
      cookies = { tenantId: 'tenantId',
                  token: 'token',
                  endpoint: 'endpoint' };
      auth = {};
      controller = new AutoLoginController(scope, location, cookies, auth);
      mixpanel = { track: function(){} }; //We are dependent on this being a global var
    });

    it('should assign autologin callbacks and method to the scope', function(){
      expect(scope.auto_login_success).not.toBe(null);
      expect(scope.auto_login_fail).not.toBe(null);
      expect(scope.autoLogIn).not.toBe(null);
    });

    describe('auto_login_fail', function(){
      it('should track the failure with mixpanel', function(){
        sinon.spy(mixpanel, 'track');
        scope.auto_login_fail({ statusText: 'blah' });

        expect(mixpanel.track.getCall(0).args[0]).toEqual('Log In Failed');
        expect(mixpanel.track.getCall(0).args[1]).toEqual({ 'problem': 'blah' });
      });

      it('should set the location path', function(){
        sinon.spy(location, 'path');
        scope.auto_login_fail({ statusText: 'blah' });

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
      it('should call authenticate with proper args', function(){
        auth.authenticate = function(){};
        sinon.spy(auth, 'authenticate');
        scope.autoLogIn();

        expect(auth.authenticate.getCall(0).args[0]).toEqual({ uri: 'endpoint' });
        expect(auth.authenticate.getCall(0).args[1]).toBeNull();
        expect(auth.authenticate.getCall(0).args[2]).toBeNull();
        expect(auth.authenticate.getCall(0).args[3]).toBeNull();
        expect(auth.authenticate.getCall(0).args[4]).toEqual('token');
        expect(auth.authenticate.getCall(0).args[5]).toEqual('tenantId');
        expect(auth.authenticate.getCall(0).args[6]).toEqual(scope.auto_login_success);
        expect(auth.authenticate.getCall(0).args[7]).toEqual(scope.auto_login_fail);
      });
    });
  });
});
