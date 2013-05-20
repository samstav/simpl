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
    api_stub = { get: emptyFunction };
    controller = new AppController(scope, http, location, resource, cookies, auth);
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

});
