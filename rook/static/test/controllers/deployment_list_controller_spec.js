describe('DeploymentListController', function(){
  var scope,
      location,
      http,
      resource,
      scroll,
      items,
      navbar,
      pagination,
      auth,
      $q,
      cmTenant,
      controller,
      emptyResponse;

  beforeEach(function(){
    scope = { $watch: emptyFunction };
    location = { search: sinon.stub().returns({}), replace: emptyFunction, path: sinon.stub().returns('/1/deployments') };
    http = {};
    resource = { get: sinon.spy() };
    scroll = {};
    items = {};
    navbar = { highlight: emptyFunction };
    pagination = { buildPaginator: sinon.stub().returns({ changed_params: sinon.spy() }) };
    auth = { context: {} };
    $q = { all: sinon.stub().returns( sinon.spy() ), defer: sinon.stub() };
    cmTenant = {};
    controller = new DeploymentListController(scope, location, http, resource, scroll, items, navbar, pagination, auth, $q, cmTenant);
    emptyResponse = { get: emptyFunction };
  });

  describe('initialization', function(){
    describe('load', function(){
      var get_spy,
          resource_spy;

      beforeEach(function(){
        get_spy = undefined;
        resource_spy = undefined;
      });

      it('should setup the url and get the resource with the tenantId', function(){
        get_spy = sinon.spy();
        resource = function(){ return { get: get_spy }; };
        resource_spy = sinon.spy(resource);

        auth.context.tenantId = 'cats';
        controller = new DeploymentListController(scope, location, http, resource_spy, scroll, items, navbar, pagination, auth);
        scope.load();

        expect(resource_spy.getCall(0).args[0]).toEqual('/1/deployments.json');
        expect(get_spy.getCall(0).args[0]).toEqual({ tenantId: 'cats' });
      });

      it('should pass in pagination params to the resource call', function(){
        pagination.buildPaginator.returns({ offset: 20, limit: 30, changed_params: emptyFunction });
        location = { search: sinon.stub().returns({ offset: 20, limit: 30 }), replace: emptyFunction, path: sinon.stub().returns('/123/deployments') };
        get_spy = sinon.spy();
        resource = function(){ return { get: get_spy }; };
        resource_spy = sinon.spy(resource);

        controller = new DeploymentListController(scope, location, http, resource_spy, scroll, items, navbar, pagination, auth);
        scope.load();
        expect(resource_spy.getCall(0).args[0]).toEqual('/123/deployments.json');
        expect(get_spy.getCall(0).args[0].offset).toEqual(20);
        expect(get_spy.getCall(0).args[0].limit).toEqual(30);
      });

      it('should use adjusted pagination params from the paginator', function(){
        pagination.buildPaginator.returns({ offset: 20, limit: 30, changed_params: emptyFunction });
        location = { search: sinon.stub().returns({ offset: 25, limit: 30 }), replace: emptyFunction, path: sinon.stub().returns('/123/deployments') };
        get_spy = sinon.spy();
        resource = function(){ return { get: get_spy }; };
        resource_spy = sinon.spy(resource);

        controller = new DeploymentListController(scope, location, http, resource_spy, scroll, items, navbar, pagination, auth);
        scope.load();
        expect(resource_spy.getCall(0).args[0]).toEqual('/123/deployments.json');
        expect(get_spy.getCall(0).args[0].offset).toEqual(20);
        expect(get_spy.getCall(0).args[0].limit).toEqual(30);
      });

      it('should pass through url options to checkmate', function(){
        location = { search: sinon.stub().returns({ show_deleted: true, cats: 'dogs' }), replace: emptyFunction, path: sinon.stub().returns('/123/deployments') };
        get_spy = sinon.spy();
        resource = function(){ return { get: get_spy }; };
        resource_spy = sinon.spy(resource);

        controller = new DeploymentListController(scope, location, http, resource_spy, scroll, items, navbar, pagination, auth);
        scope.load();
        expect(resource_spy.getCall(0).args[0]).toEqual('/123/deployments.json');
        expect(get_spy.getCall(0).args[0].show_deleted).toEqual(true);
        expect(get_spy.getCall(0).args[0].cats).toEqual('dogs');
      });
    });
  });

  describe('__tenants', function() {
    it('should default to empty object', function() {
      expect(scope.__tenants).toEqual({});
    });
  });

  describe('__content_loaded', function() {
    it('should default to false', function() {
      expect(scope.__content_loaded).toBe(false);
    });
  });

  describe('default_tags', function() {
    it('should contain main Rackspace tags', function() {
      expect(scope.default_tags).toEqual(['RackConnect', 'Managed', 'Racker', 'Internal']);
    });
  });

  describe('#tenant_tags', function() {
    it('should return the tags of a given tenant', function() {
      scope.__tenants = { '666666': { id: '666666', tags: ['faketag'] } };
      expect(scope.tenant_tags('666666')).toEqual(['faketag']);
    });

    it('should return an empty array if tenant is not cached', function() {
      scope.__tenants = {};
      expect(scope.tenant_tags('666666')).toEqual([]);
    });

    it('should return an empty array if tenant has no tags defined', function() {
      scope.__tenants = { '666666': { id: '666666' } };
      expect(scope.tenant_tags('666666')).toEqual([]);
    });
  });

  describe('#get_tenant', function() {
    it('should return cached tenant if one exists', function() {
      scope.__tenants['123'] = { id: 123 };
      expect(scope.get_tenant(123)).toEqual({id:123});
    });

    it('should fetch tenant if not yet cached', function() {
      scope.__tenants['123'] = undefined;
      cmTenant.get = sinon.stub().returns({id:123});
      expect(scope.get_tenant(123)).toEqual({id:123});
    });
  });

  describe('#toggle_tag', function() {
    beforeEach(function() {
      scope.has_tag = sinon.stub();
      spyOn(scope, 'add_tag');
      spyOn(scope, 'remove_tag');
    });

    it('should add tag to tenant if tag not yet added', function() {
      scope.has_tag.returns(false);
      scope.toggle_tag(123, 'faketag');
      expect(scope.add_tag).toHaveBeenCalledWith(123, 'faketag');
    });

    it('should remove tag from tenant if tag already set', function() {
      scope.has_tag.returns(true);
      scope.toggle_tag(123, 'faketag');
      expect(scope.remove_tag).toHaveBeenCalledWith(123, 'faketag');
    });
  });

  describe('#add_tag', function() {
    it('should add tag to tenant', function() {
      scope.get_tenant = sinon.stub().returns({ id: 123 });
      cmTenant.add_tag = sinon.spy();
      scope.add_tag(123, 'faketag');
      expect(cmTenant.add_tag).toHaveBeenCalledWith({id:123}, 'faketag')
    });
  });

  describe('#remove_tag', function() {
    it('should add tag to tenant', function() {
      scope.get_tenant = sinon.stub().returns({ id: 123 });
      cmTenant.remove_tag = sinon.spy();
      scope.remove_tag(123, 'faketag');
      expect(cmTenant.remove_tag).toHaveBeenCalledWith({id:123}, 'faketag')
    });
  });

  describe('#has_tag', function() {
    it('should return false if content not yet loaded', function() {
      scope.__content_loaded = false;
      expect(scope.has_tag(123, 'faketag')).toBe(false);
    });

    describe('when content is loaded', function() {
      beforeEach(function() {
        scope.__content_loaded = true;
      });

      it('should return true if tenant has tag', function() {
        spyOn(scope, 'get_tenant').andReturn({id:123, tags: ['faketag']});
        expect(scope.has_tag(123, 'faketag')).toBe(true);
      });

      it('should return false if tenant does not have any tags', function() {
        spyOn(scope, 'get_tenant').andReturn({id:123});
        expect(scope.has_tag(123, 'faketag')).toBeFalsy();
      });

      it('should return false if tenant does not have that specific tag', function() {
        spyOn(scope, 'get_tenant').andReturn({id:123, tags: ['othertag']});
        expect(scope.has_tag(123, 'faketag')).toBe(false);
      });
    });
  });

  describe('#get_tenant_ids', function() {
    it('should return an empty array if no deployment is passed', function() {
      expect(scope.get_tenant_ids()).toEqual([]);
    });

    it('should return an array with no undefined/null tenant IDs', function() {
      var deployments = [{tenantId: undefined}, {tenantId: null}];
      expect(scope.get_tenant_ids(deployments)).toEqual([]);
    });

    it('should return a list of tenant IDS for the given deployments', function() {
      var deployments = [{tenantId: '123'}];
      expect(scope.get_tenant_ids(deployments)).toEqual(['123']);
    });

    it('should return a unique list of tenant IDs for given deployments', function() {
      var deployments = [{tenantId: '123'}, {tenantId: '234'}, {tenantId: '123'}];
      expect(scope.get_tenant_ids(deployments).length).toBe(2);
    });
  });

  describe('#load_tenant_info', function() {
    beforeEach(function() {
      auth.is_admin = sinon.stub();
    });

    it('should not load tags if user is not an admin', function() {
      auth.is_admin.returns(false);
      scope.load_tenant_info();
      expect($q.all).toHaveBeenCalledWith([]);
    });

    describe('when user is admin', function() {
      beforeEach(function() {
        auth.is_admin.returns(true);
        $q.defer.returns({ promise: 'fakepromise' });
        cmTenant.get = sinon.spy();
      });

      it('should should create a promise for each tenant ID', function() {
        var tenant_ids = [123, 234, 345];
        scope.load_tenant_info(tenant_ids);
        expect($q.all.getCall(0).args[0].length).toBe(3);
      });

      it('should call server to get each tenant ID', function() {
        var tenant_ids = [123];
        scope.load_tenant_info(tenant_ids);
        expect(cmTenant.get).toHaveBeenCalled();
      });

      it('should not send calls to get invalid tenant IDs', function() {
        var tenant_ids = [null, undefined];
        scope.load_tenant_info(tenant_ids);
        expect(cmTenant.get).not.toHaveBeenCalled();
      });
    });
  });

  describe('#mark_content_as_loaded', function() {
    it('should mark content as loaded', function() {
      scope.mark_content_as_loaded();
      expect(scope.__content_loaded).toBe(true);
    });
  });

  describe('#is_content_loaded', function() {
    it('should be true if content is loaded', function() {
      scope.__content_loaded = true;
      expect(scope.is_content_loaded()).toBe(true);
    });

    it('should be false if content not yet loaded', function() {
      scope.__content_loaded = false;
      expect(scope.is_content_loaded()).toBe(false);
    });
  });
});
