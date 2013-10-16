describe('LoginModalController', function() {
  var $rootScope,
      $scope,
      $modalInstance,
      auth,
      $route,
      $controller;

  beforeEach(module('checkmate'));

  beforeEach(inject(function($injector) {
    $rootScope = $injector.get('$rootScope');
    $controller = $injector.get('$controller');
    auth = $injector.get('auth');
    $route = $injector.get('$route');

    var $q = $injector.get('$q');
    $modalInstance = { result: $q.defer().promise, close: sinon.spy() };
    $scope = $rootScope.$new();
    $controller('AppController', { $scope: $scope });

    var services = {
      $scope: $scope,
      $modalInstance: $modalInstance,
      auth: auth,
      $route: $route
    };
    $controller('LoginModalController', services);
  }));

  describe('#logIn', function() {
    beforeEach(function() {
      auth.authenticate = sinon.stub().returns({ then: emptyFunction });
      $scope.get_selected_endpoint = sinon.stub().returns({ uri: "fakeendpoint" });
      $scope.logIn();
    });

    it('should call try to authenticate the user', function() {
      expect(auth.authenticate).toHaveBeenCalled();
    });
  });

  describe('#clear_login_form', function() {
    beforeEach(function() {
      auth.error_message = 'fakeerror';
      $scope.bound_creds.username = 'asdf';
      $scope.bound_creds.password = 'qwer';
      $scope.bound_creds.apikey   = 'zxcv';
      $scope.clear_login_form();
    });

    it('should clear username form field', function() {
      expect($scope.bound_creds.username).toEqual(null);
    });

    it('should clear password form field', function() {
      expect($scope.bound_creds.username).toEqual(null);
    });

    it('should clear API Key form field', function() {
      expect($scope.bound_creds.username).toEqual(null);
    });

    it('should clear error messages', function() {
      expect(auth.error_message).toEqual(null);
    });
  });

  describe('#on_auth_failed', function() {
    beforeEach(function() {
      var response = { status: "fakestatustext" };
      spyOn(mixpanel, 'track');
      $scope.on_auth_failed(response);
    });

    it('should log response to mixpanel', function() {
      expect(mixpanel.track).toHaveBeenCalledWith('Log In Failed', { problem: "fakestatustext" });
    });

    it('should add an error message to auth service', function() {
      expect(auth.error_message).toEqual("fakestatustext. Check that you typed in the correct credentials.");
    });
  });

  describe('#on_auth_success', function() {
    beforeEach(function() {
      $modalInstance.close = sinon.spy();
      auth.identity = { username: "fakeusername" };
      $route.reload = sinon.spy();
      $scope.on_auth_success();
    });

    it('should reset bound username', function() {
      expect($scope.bound_creds.username).toBeFalsy();
    });

    it('should reset bound password', function() {
      expect($scope.bound_creds.password).toBeFalsy();
    });

    it('should reset bound apikey', function() {
      expect($scope.bound_creds.apikey).toBeFalsy();
    });

    it('should clear auth error message', function() {
      expect(auth.error_message).toBeFalsy();
    });

    it('should close the login prompt', function() {
      expect($modalInstance.close).toHaveBeenCalled();
    });

    it('should reload the current route', function() {
      expect($route.reload).toHaveBeenCalled();
    });
  });

});
