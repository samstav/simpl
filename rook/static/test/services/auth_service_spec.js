describe('auth Service', function(){

  var request,
      response,
      endpoint,
      headers,
      params,
      user;

  beforeEach(module('checkmate.services'));
  beforeEach(inject(function(auth, $resource, $rootScope){
    this.auth = auth;
    request = { getResponseHeader: emptyFunction };
    user = {};
    response = { access: { user: user, token: emptyFunction } };
    endpoint = {};
    headers = sinon.stub().returns('True');
    params = { headers: headers, endpoint: endpoint };
  }));

  describe('create_identity', function(){
    it('should create an identity object based on response, and params', function(){
      expect(this.auth.create_identity(response, params)).not.toBe(null);
    });

    it('should assign is_admin to true if the X-AuthZ-Admin header is True', function(){
      headers = sinon.stub().returns('True');
      params = { headers: headers, endpoint: endpoint };
      expect(this.auth.create_identity(response, params).is_admin).toBeTruthy();
    });

    it('should assign is_admin to false if the X-AuthZ-Admin header is not "True"', function(){
      headers = sinon.stub().returns('kinda true');
      params = { headers: headers, endpoint: endpoint };
      expect(this.auth.create_identity(response, params).is_admin).toBeFalsy();
    });

    it('should set username to the access user name if it is present', function(){
      user = { name: 'batman' };
      response = { access: { user: user, token: emptyFunction } };
      expect(this.auth.create_identity(response, params).username).toEqual('batman');
    });

    it('should set username to the access user id if user name is not present', function(){
      user = { id: 'robin' };
      response = { access: { user: user, token: emptyFunction } };
      expect(this.auth.create_identity(response, params).username).toEqual('robin');
    });
  });

  describe('#generate_auth_data', function() {
    var token, tenant, apikey, username, password, target;

    beforeEach(function() {
      token = 'faketoken';
      tenant = 'faketenant';
      apikey = 'fakeapikey';
      fakepinrsa = 'fakepinrsa';
      username = 'fakeusername';
      password = 'fakepassword';
      target = 'faketarget';
    });

    it('should generate token and tenant auth body', function() {
      auth_body = '{"auth":{"token":{"id":"faketoken"},"tenantId":"faketenant"}}';
      expect(this.auth.generate_auth_data(token, tenant, null, null, null, null, null)).toEqual(auth_body);
    });

    it('should generate username and apikey auth body', function() {
      auth_body = '{"auth":{"RAX-KSKEY:apiKeyCredentials":{"username":"fakeusername","apiKey":"fakeapikey"}}}';
      expect(this.auth.generate_auth_data(null, null, apikey, null, username, null, null)).toEqual(auth_body);
    });

    it('should generate username and password auth body for specific target', function() {
      target = "https://identity-internal.api.rackspacecloud.com/v2.0/tokens";
      auth_body = '{"auth":{"RAX-AUTH:domain":{"name":"Rackspace"},"passwordCredentials":{"username":"fakeusername","password":"fakepassword"}}}';
      expect(this.auth.generate_auth_data(null, null, null, null, username, password, target)).toEqual(auth_body);
    });

    it('should generate username and password auth body for generic targets', function() {
      auth_body = '{"auth":{"passwordCredentials":{"username":"fakeusername","password":"fakepassword"}}}';
      expect(this.auth.generate_auth_data(null, null, null, null, username, password, target)).toEqual(auth_body);
    });

    it('should not generate auth body without token, username or password', function() {
      expect(this.auth.generate_auth_data(null, null, null, null, null, null, target)).toBeFalsy();
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
      }; // response.access.token.tenant.id
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
        var context = this.auth.create_context(response, endpoint);
        expect(context.tenantId).toBe(null);
        expect(context.catalog).toEqual({});
        expect(context.impersonated).toBe(false);
      });

      it('should set context based on different endpoint schemes with tenant', function() {
        var context = this.auth.create_context(response, endpoint);
        expect(context.impersonated).toBe(false);
        expect(context.catalog).toEqual({});
        expect(context.tenantId).toEqual('fakeid');
      });

      it('should set context based on different endpoint schemes without tenant', function() {
        delete response.access.token.tenant;
        this.auth.fetch_identity_tenants = jasmine.createSpy('fetch_identity_tenants');
        var context = this.auth.create_context(response, endpoint);
        expect(context.impersonated).toBe(false);
        expect(context.catalog).toEqual({});
        expect(context.tenantId).toEqual(null);
        expect(this.auth.fetch_identity_tenants).toHaveBeenCalled();
      });
    });

    it('should get context regions from response', function() {
      this.auth.get_regions = jasmine.createSpy('get_regions');
      this.auth.create_context(response, endpoint);
      expect(this.auth.get_regions).toHaveBeenCalled();
    });

  });

  describe('#save_context', function() {
    beforeEach(function() {
      context1 = { username: 'user1', id: 1 };
      context2 = { username: 'user2', id: 2 };
    });

    it('should save context after impersonating user', function() {
      this.auth.save_context(context1);
      expect(this.auth.identity.tenants).not.toBe(null);
      expect(this.auth.identity.tenants.length).toBe(1);
    });

    it('should save two or more contexts after impersonating users', function() {
      this.auth.save_context(context1);
      this.auth.save_context(context2);
      expect(this.auth.identity.tenants.length).toBe(2);
    });

    it('should save contexts to the beginning of the array', function() {
      this.auth.save_context(context1);
      this.auth.save_context(context2);
      expect(this.auth.identity.tenants[0].username).toBe('user2');
    });

    it('should not save the same context twice', function() {
      this.auth.save_context(context1);
      this.auth.save_context(context1);
      expect(this.auth.identity.tenants.length).toBe(1);
    });

    it('should save a new instace of contexts, to prevent outside changes', function() {
      this.auth.save_context(context1);
      context1.username = 'userX';
      this.auth.save_context(context1);
      expect(this.auth.identity.tenants.length).toBe(2);
    });

    it('should not store more than 10 contexts', function() {
      for(var num=1 ; num<=11 ; num++) {
        context1.username = 'user' + num;
        this.auth.save_context(context1);
      }
      expect(this.auth.identity.tenants.length).toBe(10);
    });
  });

  describe('parseWWWAuthenticateHeaders', function(){
    it('should parse a header with a valid uri realm, scheme, and priority', function(){
      var headers = 'Keystone uri="https://identity.api.rackspacecloud.com/v2.0/tokens" realm="US Cloud" priority="42"';
      this.auth.parseWWWAuthenticateHeaders(headers);
      expect(this.auth.endpoints).toEqual([ { scheme : 'Keystone', realm : 'US Cloud', uri : 'https://identity.api.rackspacecloud.com/v2.0/tokens', priority: 42 } ]);
    });

    it('should sort endpoints by priority', function(){
      var header1 = 'Keystone uri="https://identity.api.rackspacecloud.com/v2.0/tokens" realm="US Cloud" priority="42"';
      var expected_endpoint1 = { scheme : 'Keystone', realm : 'US Cloud', uri : 'https://identity.api.rackspacecloud.com/v2.0/tokens', priority: 42 };

      var header2 = 'Keystone uri="https://identity.api.rackspacecloud.com/v2.0/tokens" realm="US Cloud" priority="52"';
      var expected_endpoint2 = { scheme : 'Keystone', realm : 'US Cloud', uri : 'https://identity.api.rackspacecloud.com/v2.0/tokens', priority: 52 };

      var header3 = 'Keystone uri="https://identity.api.rackspacecloud.com/v2.0/tokens" realm="US Cloud" priority="9001"';
      var expected_endpoint3 = { scheme : 'Keystone', realm : 'US Cloud', uri : 'https://identity.api.rackspacecloud.com/v2.0/tokens', priority: 9001 };

      var headers = [header2, header3, header1].join(',');

      this.auth.parseWWWAuthenticateHeaders(headers);
      expect(this.auth.endpoints).toEqual([expected_endpoint1, expected_endpoint2, expected_endpoint3]);
    });

    it('should sort endpoints without a priority at the end of the list', function(){
      var header1 = 'Keystone uri="https://identity.api.rackspacecloud.com/v2.0/tokens" realm="US Cloud" priority="42"';
      var expected_endpoint1 = { scheme : 'Keystone', realm : 'US Cloud', uri : 'https://identity.api.rackspacecloud.com/v2.0/tokens', priority: 42 };

      var header2 = 'Keystone uri="https://identity.api.rackspacecloud.com/v2.0/tokens" realm="US Cloud" priority="52"';
      var expected_endpoint2 = { scheme : 'Keystone', realm : 'US Cloud', uri : 'https://identity.api.rackspacecloud.com/v2.0/tokens', priority: 52 };

      var header3 = 'Keystone uri="https://identity.api.rackspacecloud.com/v2.0/tokens" realm="US Cloud"';
      var expected_endpoint3 = { scheme : 'Keystone', realm : 'US Cloud', uri : 'https://identity.api.rackspacecloud.com/v2.0/tokens' };

      var headers = [header2, header3, header1].join(',');

      this.auth.parseWWWAuthenticateHeaders(headers);
      expect(this.auth.endpoints).toEqual([expected_endpoint1, expected_endpoint2, expected_endpoint3]);
    });

    it('should sort endpoints without a priority in alphabetical order', function(){
      var header1 = 'Keystone uri="https://identity.api.rackspacecloud.com/v2.0/tokens" realm="Captain America" priority="1"';
      var expected_endpoint1 = { scheme : 'Keystone', realm : 'Captain America', uri : 'https://identity.api.rackspacecloud.com/v2.0/tokens', priority: 1 };

      var header2 = 'Keystone uri="https://identity.api.rackspacecloud.com/v2.0/tokens" realm="Abba"';
      var expected_endpoint2 = { scheme : 'Keystone', realm : 'Abba', uri : 'https://identity.api.rackspacecloud.com/v2.0/tokens' };

      var header3 = 'Keystone uri="https://identity.api.rackspacecloud.com/v2.0/tokens" realm="alpha"';
      var expected_endpoint3 = { scheme : 'Keystone', realm : 'alpha', uri : 'https://identity.api.rackspacecloud.com/v2.0/tokens' };

      var header4 = 'Keystone uri="https://identity.api.rackspacecloud.com/v2.0/tokens" realm="Arkansas"';
      var expected_endpoint4 = { scheme : 'Keystone', realm : 'Arkansas', uri : 'https://identity.api.rackspacecloud.com/v2.0/tokens' };

      var headers = [header2, header3, header1, header4].join(',');

      this.auth.parseWWWAuthenticateHeaders(headers);
      expect(this.auth.endpoints).toEqual([expected_endpoint1, expected_endpoint2, expected_endpoint3, expected_endpoint4]);
    });

    it('should not include endpoints that dont parse', function(){
      var header1 = 'Keystone uri="https://identity.api.rackspacecloud.com/v2.0/tokens" realm=iforgotquoteshere priority="1"';
      var header2 = 'Keystone urinetrouble="identity.api.rackspacecloud.com/v2.0/tokens" whatsthisparam="Captain America" priority="1"';

      var headers = [header1, header2].join(',');

      this.auth.parseWWWAuthenticateHeaders(headers);
      expect(this.auth.endpoints).toEqual([]);
    });
  });
});
