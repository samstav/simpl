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

    it('should not generate impersonation call data if not GlobalAuth', function() {
      var endpoint_type = 'fakeendpoint';
      expect(this.auth.generate_impersonation_data(username, endpoint_type )).toBe('{}');
    });

    it('should generate impersonation call data if GlobalAuth', function() {
      var endpoint_type = 'GlobalAuth';
      var expected_json = '{"RAX-AUTH:impersonation":{"user":{"username":"fakeusername"},"expire-in-seconds":10800}}';
      expect(this.auth.generate_impersonation_data(username, endpoint_type )).toBe(expected_json);
    });

  });

  describe('#create_context', function() {
    var response, endpoint;

    beforeEach(function() {
      response = {
        access: {
          user: { name: 'fakename' },
          token: { tenant: { id: 'fakeid' } },
          serviceCatalog: {},
        }
      };
      endpoint = { uri: 'fakeuri', scheme: 'fakescheme' };
    });

    it('should create a context based on a response', function() {
      expect(this.auth.create_context(response, endpoint)).not.toBe(null);
    });

    it('should set context user according to response object', function() {
      expect(this.auth.create_context(response, endpoint).user).toEqual({ name: 'fakename' });
    });

    it('should set context token according to response object', function() {
      expect(this.auth.create_context(response, endpoint).token).toEqual({ tenant: { id: 'fakeid' } });
    });

    it('should set context auth_url according to response object', function() {
      expect(this.auth.create_context(response, endpoint).auth_url).toEqual('fakeuri');
    });

    it('should set context username user.name if it is present', function() {
      expect(this.auth.create_context(response, endpoint).username).toEqual('fakename');
    });

    it('should set context username user.id if name does not exist', function() {
      delete response.access.user.name;
      response.access.user.id = 'fakeuserid';
      expect(this.auth.create_context(response, endpoint).username).toEqual('fakeuserid');
    });

    describe('#context and endpoint schemes', function() {
      it('should set context based on GlobalAuth', function() {
        endpoint.scheme = 'GlobalAuth';
        this.auth.create_context(response, endpoint);
        expect(this.auth.context.tenantId).toBe(null);
        expect(this.auth.context.catalog).toEqual({});
        expect(this.auth.context.impersonated).toBe(false);
      });

      it('should set context based on different endpoint schemes with tenant', function() {
        this.auth.create_context(response, endpoint);
        expect(this.auth.context.impersonated).toBe(false);
        expect(this.auth.context.catalog).toEqual({});
        expect(this.auth.context.tenantId).toEqual('fakeid');
      });

      it('should set context based on different endpoint schemes without tenant', function() {
        delete response.access.token.tenant;
        this.auth.fetch_identity_tenants = jasmine.createSpy('fetch_identity_tenants');
        this.auth.create_context(response, endpoint);
        expect(this.auth.context.impersonated).toBe(false);
        expect(this.auth.context.catalog).toEqual({});
        expect(this.auth.context.tenantId).toEqual(null);
        expect(this.auth.fetch_identity_tenants).toHaveBeenCalled();
      });
    });

    it('should get context regions from response', function() {
      this.auth.get_regions = jasmine.createSpy('get_regions');
      this.auth.create_context(response, endpoint);
      expect(this.auth.get_regions).toHaveBeenCalled();
    });

  });

});
