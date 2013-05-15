describe('auth Service', function(){

  var request, response, endpoint, user;
  beforeEach(module('checkmate.services'));
  beforeEach(inject(function(auth, $resource, $rootScope){
    this.auth = auth;
    request = { getResponseHeader: emptyFunction };
    user = {};
    response = { access: { user: user, token: emptyFunction } };
    endpoint = {};
  }));

  describe('create_identity', function(){
    it('should create an identity object based on request, response, and endpoint', function(){
      expect(this.auth.create_identity(request, response, endpoint)).not.toBe(null);
    });

    it('should assign is_admin to true if the X-AuthZ-Admin header is True', function(){
      request = { getResponseHeader: function(){ return 'True'; } };
      expect(this.auth.create_identity(request, response, endpoint).is_admin).toBeTruthy();
    });

    it('should assign is_admin to false if the X-AuthZ-Admin header is not "True"', function(){
      request = { getResponseHeader: function(){ return 'Truish'; } };
      expect(this.auth.create_identity(request, response, endpoint).is_admin).toBeFalsy();
    });

    it('should set username to the access user name if it is present', function(){
      user = { name: 'batman' };
      response = { access: { user: user, token: emptyFunction } };
      expect(this.auth.create_identity(request, response, endpoint).username).toEqual('batman');
    });

    it('should set username to the access user id if user name is not present', function(){
      user = { id: 'robin' };
      response = { access: { user: user, token: emptyFunction } };
      expect(this.auth.create_identity(request, response, endpoint).username).toEqual('robin');
    });
  });

  describe('json data generation', function() {
    var token, tenant, apikey, username, password, target;

    beforeEach(function() {
      token = 'faketoken';
      tenant = 'faketenant';
      apikey = 'fakeapikey';
      username = 'fakeusername';
      password = 'fakepassword';
      target = 'faketarget';
    });

    it('should generate token and tenant auth body', function() {
      auth_body = '{"auth":{"token":{"id":"faketoken"},"tenantId":"faketenant"}}';
      expect(this.auth.generate_auth_data(token, tenant, null, null, null, null)).toEqual(auth_body);
    });

    it('should generate username and apikey auth body', function() {
      auth_body = '{"auth":{"RAX-KSKEY:apiKeyCredentials":{"username":"fakeusername","apiKey":"fakeapikey"}}}';
      expect(this.auth.generate_auth_data(null, null, apikey, username, null, null)).toEqual(auth_body);
    });

    it('should generate username and password auth body for specific target', function() {
      target = "https://identity-internal.api.rackspacecloud.com/v2.0/tokens";
      auth_body = '{"auth":{"RAX-AUTH:domain":{"name":"Rackspace"},"passwordCredentials":{"username":"fakeusername","password":"fakepassword"}}}';
      expect(this.auth.generate_auth_data(null, null, null, username, password, target)).toEqual(auth_body);
    });

    it('should generate username and password auth body for generic targets', function() {
      auth_body = '{"auth":{"passwordCredentials":{"username":"fakeusername","password":"fakepassword"}}}';
      expect(this.auth.generate_auth_data(null, null, null, username, password, target)).toEqual(auth_body);
    });

    it('should not generate auth body without token, username or password', function() {
      expect(this.auth.generate_auth_data(null, null, null, null, null, target)).toBeFalsy();
    });

  });
});
