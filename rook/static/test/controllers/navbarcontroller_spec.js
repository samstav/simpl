describe('NavBarController', function(){
  var scope,
      location,
      cookies,
      auth,
      http,
      controller;

  beforeEach(function() {
    scope = { '$apply': emptyFunction, loginPrompt: emptyFunction };
    location = { path: emptyFunction };
    cookies = {};
    auth = {};
    http = { pendingRequests: [] };
    controller = new NavBarController(scope, location, http);
  });

  it('should detect 0 pending http requests', function() {
    expect(scope.hasPendingRequests()).toBe(false);
  });

  it('should detect 1+ pending http requests', function() {
    http.pendingRequests = [1,2,3]
    expect(scope.hasPendingRequests()).toBe(true);
  });

});

