describe('auth Service', function(){

  var request,
      response,
      endpoint,
      headers,
      params,
      user,
      $rootScope;

  beforeEach(module('checkmate.services'));
  beforeEach(inject(function(auth, $resource, $q, _$rootScope_){
    this.auth = auth;
    request = { getResponseHeader: emptyFunction };
    user = {};
    response = { access: { user: user, token: emptyFunction } };
    endpoint = {};
    headers = sinon.stub().returns('True');
    params = { headers: headers, endpoint: endpoint };
    $rootScope = _$rootScope_;
  }));

  describe('#is_admin', function() {
    beforeEach(function() {
      this.auth.identity.is_admin = true;
    });

    it('should default to false', function() {
      delete this.auth.identity.is_admin;
      expect(this.auth.is_admin()).toBeFalsy();
    });

    it('should return false when current identity is not an admin', function() {
      this.auth.identity.is_admin = false;
      expect(this.auth.is_admin()).toBeFalsy();
    });

    it('should return true when current identity is an admin', function() {
      expect(this.auth.is_admin()).toBeTruthy();
    });

    it('should return true even if admin is impersonating', function() {
      this.auth.is_impersonating = sinon.stub().returns(true);
      expect(this.auth.is_admin()).toBeTruthy();
    });

    describe('when in strict mode', function() {
      it('should return false if admin is impersonating', function() {
        this.auth.is_impersonating = sinon.stub().returns(true);
        expect(this.auth.is_admin(true)).toBeFalsy();
      });
    });
  });

  describe('#is_logged_in', function() {
    it('should return true if identity has loggedIn attribute', function() {
      this.auth.identity = { loggedIn: true };
      expect(this.auth.is_logged_in()).toBe(true);
    });

    it('should return false if identity does not have loggedIn attribute', function() {
      this.auth.identity = { loggedIn: false };
      expect(this.auth.is_logged_in()).toBe(false);
    });

    it('should return false if identity has not been set yet', function() {
      this.auth.identity = {};
      expect(this.auth.is_logged_in()).toBeFalsy();
    });
  });

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
    var token, tenant, apikey, username, password, scheme;

    beforeEach(function() {
      token = 'faketoken';
      tenant = 'faketenant';
      apikey = 'fakeapikey';
      fakepinrsa = 'fakepinrsa';
      username = 'fakeusername';
      password = 'fakepassword';
      scheme = 'fakescheme';
    });

    it('should generate token and tenant auth body', function() {
      auth_body = '{"auth":{"token":{"id":"faketoken"},"tenantId":"faketenant"}}';
      expect(this.auth.generate_auth_data(token, tenant, null, null, null, null, null)).toEqual(auth_body);
    });

    it('should generate username and apikey auth body', function() {
      auth_body = '{"auth":{"RAX-KSKEY:apiKeyCredentials":{"username":"fakeusername","apiKey":"fakeapikey"}}}';
      expect(this.auth.generate_auth_data(null, null, apikey, null, username, null, null)).toEqual(auth_body);
    });

    it('should generate username and password auth body for specific scheme', function() {
      scheme = "GlobalAuth";
      auth_body = '{"auth":{"RAX-AUTH:domain":{"name":"Rackspace"},"passwordCredentials":{"username":"fakeusername","password":"fakepassword"}}}';
      expect(this.auth.generate_auth_data(null, null, null, null, username, password, scheme)).toEqual(auth_body);
    });

    it('should generate username and password auth body for generic schemes', function() {
      auth_body = '{"auth":{"passwordCredentials":{"username":"fakeusername","password":"fakepassword"}}}';
      expect(this.auth.generate_auth_data(null, null, null, null, username, password, scheme)).toEqual(auth_body);
    });

    it('should not generate auth body without token, username or password', function() {
      expect(this.auth.generate_auth_data(null, null, null, null, null, null, scheme)).toBeFalsy();
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
    var response, endpoint, params;

    beforeEach(function() {
      response = {
        access: {
          user: { name: 'fakename' },
          token: { tenant: { id: 'fakeid' } },
          serviceCatalog: {},
        }
      };
      endpoint = { uri: 'fakeuri', scheme: 'fakescheme' };
      params = { endpoint: endpoint };
    });

    it('should create a context based on a response', function() {
      expect(this.auth.create_context(response, params)).not.toBe(null);
    });

    it('should set context user according to response object', function() {
      expect(this.auth.create_context(response, params).user).toEqual({ name: 'fakename' });
    });

    it('should set context token according to response object', function() {
      expect(this.auth.create_context(response, params).token).toEqual({ tenant: { id: 'fakeid' } });
    });

    it('should set context auth_url according to response object', function() {
      expect(this.auth.create_context(response, params).auth_url).toEqual('fakeuri');
    });

    it('should set context username user.name if it is present', function() {
      expect(this.auth.create_context(response, params).username).toEqual('fakename');
    });

    it('should set context username user.id if name does not exist', function() {
      delete response.access.user.name;
      response.access.user.id = 'fakeuserid';
      expect(this.auth.create_context(response, params).username).toEqual('fakeuserid');
    });

    describe('#context and endpoint schemes', function() {
      it('should set context based on GlobalAuth', function() {
        params.endpoint.scheme = 'GlobalAuth';
        var context = this.auth.create_context(response, params);
        expect(context.tenantId).toBe(null);
        expect(context.catalog).toEqual({});
        expect(context.impersonated).toBe(false);
      });

      it('should set context based on different endpoint schemes with tenant', function() {
        var context = this.auth.create_context(response, params);
        expect(context.impersonated).toBe(false);
        expect(context.catalog).toEqual({});
        expect(context.tenantId).toEqual('fakeid');
      });

      it('should set context based on different endpoint schemes without tenant', function() {
        delete response.access.token.tenant;
        this.auth.fetch_identity_tenants = jasmine.createSpy('fetch_identity_tenants');
        var context = this.auth.create_context(response, params);
        expect(context.impersonated).toBe(false);
        expect(context.catalog).toEqual({});
        expect(context.tenantId).toEqual(null);
        expect(this.auth.fetch_identity_tenants).toHaveBeenCalled();
      });
    });

    it('should get context regions from response', function() {
      this.auth.get_regions = jasmine.createSpy('get_regions');
      this.auth.create_context(response, params);
      expect(this.auth.get_regions).toHaveBeenCalled();
    });

  });

  describe('#cache_tenant', function() {
    beforeEach(function() {
      context1 = { username: 'user1', id: 1 };
      context2 = { username: 'user2', id: 2 };
    });

    it('should save context after impersonating user', function() {
      this.auth.cache_tenant(context1);
      expect(this.auth.cache.tenants).not.toBe(null);
      expect(this.auth.cache.tenants.length).toBe(1);
    });

    it('should save two or more contexts after impersonating users', function() {
      this.auth.cache_tenant(context1);
      this.auth.cache_tenant(context2);
      expect(this.auth.cache.tenants.length).toBe(2);
    });

    it('should save contexts to the beginning of the array', function() {
      this.auth.cache_tenant(context1);
      this.auth.cache_tenant(context2);
      expect(this.auth.cache.tenants[0].username).toBe('user2');
    });

    it('should not save the same context twice', function() {
      this.auth.cache_tenant(context1);
      this.auth.cache_tenant(context1);
      expect(this.auth.cache.tenants.length).toBe(1);
    });

    it('should save a new instace of contexts, to prevent outside changes', function() {
      this.auth.cache_tenant(context1);
      context1.username = 'userX';
      this.auth.cache_tenant(context1);
      expect(this.auth.cache.tenants.length).toBe(2);
    });

    it('should not store more than 10 contexts', function() {
      for(var num=1 ; num<=11 ; num++) {
        context1.username = 'user' + num;
        this.auth.cache_tenant(context1);
      }
      expect(this.auth.cache.tenants.length).toBe(10);
    });
  });

  describe('#get_cached_tenant', function() {
    it('should return false if no username or tenant ID is passed', function() {
      expect(this.auth.get_cached_tenant()).toBe(false);
    });

    it('should return false if identity does not have any tenants', function() {
      this.auth.identity = {};
      expect(this.auth.get_cached_tenant()).toBe(false);
    });

    describe('when context does not exist', function() {
      it('should return false', function() {
        this.auth.identity = { tenants: [] };
        expect(this.auth.get_cached_tenant('fakeinfo')).toBe(false);
      });
    });

    describe('when context exists', function() {
      beforeEach(function() {
        this.auth.cache.tenants = [
          { username: 'notvalidname', tenantId: 'someID', info: 'otherinfo' },
          { username: 'fakeusername', tenantId: 'fakeID', info: 'fakeinfo' }
        ];
      });

      it('should return context if passing a username', function() {
        expect(this.auth.get_cached_tenant('fakeusername').info).toEqual('fakeinfo');
      });

      it('should return context if passing a tenant ID', function() {
        expect(this.auth.get_cached_tenant('fakeID').info).toEqual('fakeinfo');
      });

      it('should return false if no username or tenant ID is found', function() {
        expect(this.auth.get_cached_tenant('batman')).toBe(false);
      });
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

    it('should sort endpoints with priority 0', function(){
      var header1 = 'Keystone uri="https://identity.api.rackspacecloud.com/v2.0/tokens" realm="US Cloud" priority="0"';
      var expected_endpoint1 = { scheme : 'Keystone', realm : 'US Cloud', uri : 'https://identity.api.rackspacecloud.com/v2.0/tokens', priority: 0 };

      var header2 = 'Keystone uri="https://identity.api.rackspacecloud.com/v2.0/tokens" realm="US Cloud" priority="1"';
      var expected_endpoint2 = { scheme : 'Keystone', realm : 'US Cloud', uri : 'https://identity.api.rackspacecloud.com/v2.0/tokens', priority: 1 };

      var headers = [header2, header1].join(',');

      this.auth.parseWWWAuthenticateHeaders(headers);
      expect(this.auth.endpoints).toEqual([expected_endpoint1, expected_endpoint2]);
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

  describe('#re_authenticate', function() {
    var $httpBackend;
    beforeEach(inject(function($injector) {
      $httpBackend = $injector.get('$httpBackend');
      $httpBackend.when('POST', "/authproxy/v2.0/tokens").respond(200, "fakeauth");
      spyOn(this.auth, 'generate_auth_data').andReturn("fakedata");
    }));

    it('should send a token/tenant auth call', function() {
      var promise = this.auth.re_authenticate("faketoken", "faketenant");
      var auth_response = "";
      promise.then(function(response) { auth_response = response; });
      $httpBackend.flush();
      expect(auth_response.data).toEqual("fakeauth");
    });
  });

  describe('#impersonate', function() {
    var $httpBackend, $q, deferred;

    beforeEach(inject(function($injector) {
      $httpBackend = $injector.get('$httpBackend');
      $q = $injector.get('$q');
      this.auth.identity.token = {};
      spyOn(this.auth, 'generate_impersonation_data');
      spyOn(this.auth, 'get_impersonation_url');
      spyOn(this.auth, 'impersonate_success');
      spyOn(this.auth, 'impersonate_error');
      deferred = $q.defer();
    }));

    it('- on success: should call impersonate_success', function() {
      $httpBackend.when('POST', '/authproxy').respond(200, deferred.promise);
      this.auth.impersonate("fakeusername");
      $httpBackend.flush();
      expect(this.auth.impersonate_success).toHaveBeenCalled();
    });

    it('- on error: should call impersonate_error', function() {
      $httpBackend.when('POST', '/authproxy').respond(401, deferred.promise);
      this.auth.impersonate("fakeusername");
      $httpBackend.flush();
      expect(this.auth.impersonate_error).toHaveBeenCalled();
    });
  });

  describe('#impersonate_success', function() {
    var $rootScope, $q, deferred, get_tenant_id_deferred, username;
    beforeEach(inject(function($injector) {
      $q = $injector.get('$q');
      $rootScope = $injector.get('$rootScope');;
      deferred = $q.defer();
      get_tenant_id_deferred = $q.defer();
      spyOn(this.auth, 'get_tenant_id').andReturn(get_tenant_id_deferred.promise);
      response.data = { access: { token: { id: "faketoken" } } };
      username = "fakeusername";
    }));

    describe('when context is cached', function() {
      beforeEach(function() {
        spyOn(this.auth, 'get_cached_context').andReturn({ info: 'fakeinfo' });
        spyOn(this.auth, 'check_state');
        this.auth.impersonate('batman');
      });

      it('should restore previous context', function() {
        expect(this.auth.context.info).toBe('fakeinfo');
      });

      it('should check token state after restoring context', function() {
        expect(this.auth.check_state).toHaveBeenCalled();
      });
    });

    describe('when tenant_id was retrieved', function() {
      beforeEach(function() {
        spyOn(this.auth, 'cache_tenant');
        spyOn(this.auth, 'save');
        spyOn(this.auth, 'check_state');
        spyOn(this.auth, 're_authenticate').andReturn({ then: emptyFunction });
        spyOn(deferred, 'resolve');
        get_tenant_id_deferred.resolve("666666");
      });

      it('should re-authenticate the user', function() {
        this.auth.impersonate_success(username, response, deferred);
        $rootScope.$apply();
        expect(this.auth.re_authenticate).toHaveBeenCalledWith("faketoken", "666666");
      });

      describe('and user was re-authenticated', function() {
        beforeEach(function() {
          var re_authenticate_data = { data: { access: { serviceCatalog: "fakecatalog" } }};
          var re_authenticate_deferred = $q.defer();
          this.auth.re_authenticate.andReturn(re_authenticate_deferred.promise);
          re_authenticate_deferred.resolve(re_authenticate_data);
          this.auth.impersonate_success(username, response, deferred);
          this.auth.identity.auth_url = "https://some-internal.rackspace.com/path"
          spyOn(this.auth, 'get_regions').andReturn("fakeregions");
          $rootScope.$apply();
        });

        it('should set context username', function() {
          expect(this.auth.context.username).toEqual("fakeusername");
        });

        it('should set context token', function() {
          expect(this.auth.context.token).toEqual( { id: "faketoken" } );
        });

        it('should set context auth_url', function() {
          expect(this.auth.context.auth_url).toEqual("https://some.rackspace.com/path");
        });

        it('should set tenantId', function() {
          expect(this.auth.context.tenantId).toEqual("666666");
        });

        it('should set catalog', function() {
          expect(this.auth.context.catalog).toEqual("fakecatalog");
        });

        it('should store context for future use', function() {
          expect(this.auth.cache_tenant).toHaveBeenCalled();
        });

        it('should save auth for future use', function() {
          expect(this.auth.save).toHaveBeenCalled();
        });

        it('should check authentication state', function() {
          expect(this.auth.check_state).toHaveBeenCalled();
        });

        it('should resolve the deferred promise', function() {
          expect(deferred.resolve).toHaveBeenCalled();
        });
      });

      describe('and the user could not be re-authenticated', function() {
        beforeEach(function() {
          var re_authenticate_deferred = $q.defer();
          this.auth.re_authenticate.andReturn(re_authenticate_deferred.promise);
          re_authenticate_deferred.reject("fakereject");
          spyOn(this.auth, 'impersonate_error');
          this.auth.impersonate_success(username, response, deferred);
          $rootScope.$apply();
        });

        it('should call impersonate_error', function() {
          expect(this.auth.impersonate_error).toHaveBeenCalledWith("fakereject", deferred);
        });
      });
    });

    describe('when tenant_id was not retrieved', function() {
      it('should reject deferred promise', function() {
        spyOn(this.auth, 'impersonate_error');
        get_tenant_id_deferred.reject();
        this.auth.impersonate_success(username, response, deferred);
        $rootScope.$apply();
        expect(this.auth.impersonate_error).toHaveBeenCalled();
      });
    });
  });

  describe('#impersonate_error', function() {
    it('should reject deferred promise', function() {
      var response = "fakeresponse";
      var deferred = { reject: sinon.spy() };
      this.auth.impersonate_error(response, deferred);
      expect(deferred.reject).toHaveBeenCalled();
    });
  });

  describe('#exit_impersonation', function() {
    beforeEach(function() {
      original_context = { context_info: "fakeoriginalcontext" };
      this.auth.identity.context = original_context;
      spyOn(this.auth, 'check_state');
      spyOn(this.auth, 'save');
      this.auth.exit_impersonation();
    });

    it('should restore original identity context', function() {
      expect(this.auth.context).toEqual( { context_info: "fakeoriginalcontext" } );
    });

    it('should check state to reset auth tokens', function() {
      expect(this.auth.check_state).toHaveBeenCalled();
    })

    it('should save auth information to local storage', function() {
      expect(this.auth.save).toHaveBeenCalled();
    })
  });

  describe('#is_impersonating', function() {
    beforeEach(function() {
      this.auth.identity = { username: 'admin' };
      this.auth.context = {};
    });

    it('should be true if impersonating a tenant', function() {
      this.auth.context.username = 'tenant';
      expect(this.auth.is_impersonating()).toBe(true);
    });

    it('should be false if not impersonating a tenant', function() {
      this.auth.context.username = 'admin';
      expect(this.auth.is_impersonating()).toBe(false);
    });
  });

  describe('#save', function() {
    var previous_tenants;
    beforeEach(function() {
      this.auth.cache.tenants = [
        { username: "fakeusername1", tenantId: "fakeid1", sensitive1: "sensitiveinformation1" },
        { username: "fakeusername2", tenantId: "fakeid2", sensitive2: "sensitiveinformation2" },
        { username: "fakeusername3", tenantId: "fakeid3", sensitive3: "sensitiveinformation3" },
      ];
      this.auth.save();
      previous_tenants = JSON.parse(localStorage.previous_tenants);
    });

    it('should save previous tenants information to localStorage', function() {
      expect(localStorage.previous_tenants).not.toBe(null);
    });

    it('should save previous tenant username localStorage', function() {
      expect(previous_tenants[0].username).not.toBe(undefined);
    });

    it('should save previous tenant ID to localStorage', function() {
      expect(previous_tenants[0].tenantId).not.toBe(undefined);
    });

    it('should should not save any other information from previous tenants to localStorage', function() {
      expect(previous_tenants[0].sensitive1).toBe(undefined);
      expect(Object.keys(previous_tenants[0]).length).toBe(2);
    });
  });

  describe('#logOut', function() {
    beforeEach(function() {
      checkmate.config.header_defaults = {
        headers: {
          common: {
            'X-Auth-Token': "faketoken",
            'X-Auth-Source': "fakesource",
          }
        }
      };
      spyOn(this.auth, 'clear');
      spyOn($rootScope, '$broadcast');
    });

    describe('regardless of flag status', function() {
      beforeEach(function() {
        spyOn(localStorage, 'removeItem');
        this.auth.logOut();
      });

      it('should call auth#clear', function() {
        expect(this.auth.clear).toHaveBeenCalled();
      });

      it('should clear checkmate default headers', function() {
        expect(checkmate.config.header_defaults.headers.common['X-Auth-Token']).toBe(undefined);
        expect(checkmate.config.header_defaults.headers.common['X-Auth-Source']).toBe(undefined);
      });

      it('should remove auth information from localStorage', function() {
        expect(localStorage.removeItem).toHaveBeenCalledWith('auth');
      });
    });

    it('should default broadcast to true', function() {
      this.auth.logOut();
      expect($rootScope.$broadcast).toHaveBeenCalled();
    });

    it('should broadcast logOut if flag is set to true', function() {
      this.auth.logOut(true);
      expect($rootScope.$broadcast).toHaveBeenCalled();
    });

    it('should not broadcast logOut if flag is set to false', function() {
      this.auth.logOut(false);
      expect($rootScope.$broadcast).not.toHaveBeenCalled();
    });
  });

  describe('cache', function() {
    it('should default to an emtpy object', function() {
      expect(this.auth.cache).toEqual({});
    });
  });

  describe('#cache_context', function() {
    it('should do nothing if context is empty', function() {
      this.auth.cache_context();
      expect(this.auth.cache).toEqual({});
    });

    it('should initialize cache contexts', function() {
      this.auth.cache_context({});
      expect(this.auth.cache.contexts).toEqual({});
    });

    it('should store context in cache under tenantId key', function() {
      this.auth.cache_context({ tenantId: 666 });
      expect(this.auth.cache.contexts[666]).toEqual({ tenantId: 666 });
    });

    it('should store context in cache under username key', function() {
      this.auth.cache_context({ username: 'fakeusername' });
      expect(this.auth.cache.contexts['fakeusername']).toEqual({ username: 'fakeusername' });
    });

    it('should return the cached context', function() {
      var context = this.auth.cache_context({ username: 'fakeusername' });
      expect(context).toEqual({ username: 'fakeusername' });
    });
  });

  describe('#get_cached_context', function() {
    it('should return undefined if username or tenantId are not in cache', function() {
      expect(this.auth.get_cached_context('fakeusername')).toEqual(undefined);
      expect(this.auth.get_cached_context(666)).toEqual(undefined);
    });

    it('should return the context by tenantId', function() {
      this.auth.cache.contexts = { 'fakeusername': { username: 'fakeusername' } };
      expect(this.auth.get_cached_context('fakeusername')).toEqual({username: 'fakeusername'});
    });

    it('should return the context by username', function() {
      this.auth.cache.contexts = { 666: { tenantId: 666 } };
      expect(this.auth.get_cached_context(666)).toEqual({tenantId: 666});
    });
  });
});
