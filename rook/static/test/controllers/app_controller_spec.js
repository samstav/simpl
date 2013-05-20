describe('AppController', function(){
  var scope,
      http,
      location,
      resource,
      cookies,
      auth,
      controller,
      api_stub;

  beforeEach(function(){
    scope = { $on: sinon.stub(), $root: {} };
    http = {};
    location = {};
    resource = function(){ return api_stub; };
    cookies = {};
    auth = {};
    controller = {};
    api_stub = { get: emptyFunction };
  });

  it('should display the header', function(){
    controller = new AppController(scope, http, location, resource, cookies, auth);
    expect(scope.showHeader).toBe(true);
  });

  it('should not display status', function(){
    controller = new AppController(scope, http, location, resource, cookies, auth);
    expect(scope.showStatus).toBe(false);
  });
});
