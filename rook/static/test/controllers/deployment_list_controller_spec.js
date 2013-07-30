describe('DeploymentListController', function(){
  var scope,
      $location,
      http,
      resource,
      scroll,
      items,
      navbar,
      pagination,
      auth,
      $q,
      cmTenant,
      Deployment,
      $timeout,
      $filter,
      controller,
      emptyResponse;

  beforeEach(function(){
    scope = { $watch: emptyFunction };
    $location = { search: sinon.stub().returns({}), replace: emptyFunction, path: sinon.stub().returns('/1/deployments') };
    http = {};
    resource = { get: sinon.spy() };
    scroll = {};
    items = {};
    navbar = { highlight: emptyFunction };
    pagination = { buildPaginator: sinon.stub().returns({ changed_params: sinon.spy() }) };
    auth = { context: {} };
    $q = { all: sinon.stub().returns( sinon.spy() ), defer: sinon.stub() };
    cmTenant = {};
    Deployment = {};
    $timeout = sinon.stub().returns('fake promise');
    $timeout.cancel = sinon.stub();
    $filter = sinon.stub();
    controller = new DeploymentListController(scope, $location, http, resource, scroll, items, navbar, pagination, auth, $q, cmTenant, Deployment, $timeout, $filter);
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
        controller = new DeploymentListController(scope, $location, http, resource_spy, scroll, items, navbar, pagination, auth);
        scope.load();

        expect(resource_spy.getCall(0).args[0]).toEqual('/1/deployments.json');
        expect(get_spy.getCall(0).args[0]).toEqual({ tenantId: 'cats' });
      });

      it('should pass in pagination params to the resource call', function(){
        pagination.buildPaginator.returns({ offset: 20, limit: 30, changed_params: emptyFunction });
        $location = { search: sinon.stub().returns({ offset: 20, limit: 30 }), replace: emptyFunction, path: sinon.stub().returns('/123/deployments') };
        get_spy = sinon.spy();
        resource = function(){ return { get: get_spy }; };
        resource_spy = sinon.spy(resource);

        controller = new DeploymentListController(scope, $location, http, resource_spy, scroll, items, navbar, pagination, auth);
        scope.load();
        expect(resource_spy.getCall(0).args[0]).toEqual('/123/deployments.json');
        expect(get_spy.getCall(0).args[0].offset).toEqual(20);
        expect(get_spy.getCall(0).args[0].limit).toEqual(30);
      });

      it('should use adjusted pagination params from the paginator', function(){
        pagination.buildPaginator.returns({ offset: 20, limit: 30, changed_params: emptyFunction });
        $location = { search: sinon.stub().returns({ offset: 25, limit: 30 }), replace: emptyFunction, path: sinon.stub().returns('/123/deployments') };
        get_spy = sinon.spy();
        resource = function(){ return { get: get_spy }; };
        resource_spy = sinon.spy(resource);

        controller = new DeploymentListController(scope, $location, http, resource_spy, scroll, items, navbar, pagination, auth);
        scope.load();
        expect(resource_spy.getCall(0).args[0]).toEqual('/123/deployments.json');
        expect(get_spy.getCall(0).args[0].offset).toEqual(20);
        expect(get_spy.getCall(0).args[0].limit).toEqual(30);
      });

      it('should pass through url options to checkmate', function(){
        $location = { search: sinon.stub().returns({ show_deleted: true, cats: 'dogs' }), replace: emptyFunction, path: sinon.stub().returns('/123/deployments') };
        get_spy = sinon.spy();
        resource = function(){ return { get: get_spy }; };
        resource_spy = sinon.spy(resource);

        controller = new DeploymentListController(scope, $location, http, resource_spy, scroll, items, navbar, pagination, auth);
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

  describe('#all_tags', function() {
    beforeEach(function() {
      scope.default_tags = ['a', 'b', 'c'];
      scope.__tenants = {
        123: { tags: ['x', 'y'] },
        456: { tags: ['x', 'z'] },
        789: { tags: ['y', 'z'] }
      };
    });

    it('should return the default tags if no tenants have been retrieved', function() {
      scope.__tenants = {};
      expect(scope.all_tags()).toEqual(['a', 'b', 'c']);
    });

    it('should return the default tags if tenants have no tags', function() {
      scope.__tenants[123].tags = [];
      scope.__tenants[456].tags = [];
      scope.__tenants[789].tags = [];
      expect(scope.all_tags()).toEqual(['a', 'b', 'c']);
    });

    it('should return all current tags', function() {
      expect(scope.all_tags()).toEqual(['a', 'b', 'c', 'x', 'y', 'z']);
    });

    it('should return default tags first', function() {
      var tags = scope.all_tags();
      expect(tags.splice(0, 3)).toEqual(['a', 'b', 'c']);
    });

    it('should return custom tags last', function() {
      var tags = scope.all_tags();
      expect(tags.splice(3, 3)).toEqual(['x', 'y', 'z']);
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

  describe('selected_deployments', function() {
    it('should default to empty object', function() {
      expect(scope.selected_deployments).toEqual({});
    });
  });

  describe('deployment_map', function() {
    it('should default to empty object', function() {
      expect(scope.deployment_map).toEqual({});
    });
  });

  describe('#is_selected', function() {
    it('should return true if any deployment has been selected', function() {
      scope.selected_deployments = { 123: 'somedeployment' };
      expect(scope.is_selected()).toBeTruthy();
    });

    it('should return false if no deployment has been selected', function() {
      scope.selected_deployments = {};
      expect(scope.is_selected()).toBeFalsy();
    });
  });

  describe('#select_toggle', function() {
    var deployment;
    beforeEach(function() {
      deployment = { id: 123, content: 'somecontent' };
    });

    it('should remove deployment from selected list if deployment was there', function() {
      scope.selected_deployments = { 123: true };
      scope.deployment_map = { 123: deployment };
      scope.select_toggle(deployment);
      expect(scope.is_selected[123]).toBe(undefined);
    });

    describe('if deployment was not in selected list', function() {
      beforeEach(function() {
        scope.selected_deployments = {};
        scope.select_toggle(deployment);
      });

      it('should add deployment to selected list', function() {
        expect(scope.selected_deployments[123]).not.toBe(undefined);
      });

      it('should set selected flag to true', function() {
        expect(scope.selected_deployments[123]).toBe(true);
      });

      it('should add deployment object to list', function() {
        expect(scope.deployment_map[123]).toEqual({ id: 123, content: 'somecontent' });
      });
    });
  });

  describe('#sync_deployments', function() {
    beforeEach(function() {
      scope.wrap_admin_call = sinon.spy();
    });

    it('should sync all selected deployments', function() {
      var d1 = {id: 123, created_by: 'asdf'};
      var d2 = {id: 456, created_by: 'qwer'};
      scope.selected_deployments = {
        123: true,
        456: true,
      };
      scope.deployment_map = {
        123: d1,
        456: d2,
      };
      scope.sync_deployments();
      expect(scope.wrap_admin_call).toHaveBeenCalledWith('asdf', scope.sync, d1);
      expect(scope.wrap_admin_call).toHaveBeenCalledWith('qwer', scope.sync, d2);
    });

    it('should should not sync empty list', function() {
      scope.selected_deployments = {};
      scope.sync_deployments();
      expect(scope.wrap_admin_call).not.toHaveBeenCalled();
    });
  });

  describe('query', function() {
    it('should default to empty if no search params are used', function() {
      $location.search.returns({})
      controller = new DeploymentListController(scope, $location, http, resource, scroll, items, navbar, pagination, auth, $q, cmTenant, Deployment, $timeout);
      expect(scope.query).toBe(undefined);
    });

    it('should equal to search params if present', function() {
      $location.search.returns({ search: 'foobar' })
      controller = new DeploymentListController(scope, $location, http, resource, scroll, items, navbar, pagination, auth, $q, cmTenant, Deployment, $timeout);
      expect(scope.query).toEqual('foobar');
    });
  });

  describe('filter_promise', function() {
    it('should default to null', function() {
      expect(scope.filter_promise).toBe(null);
    });
  });

  describe('filters', function() {
    it('should be an object', function() {
      expect(typeof scope.filters).toBe("object");
    });

    describe('default tenant_tag', function() {
      it('should contain four default filters for tenant_tag', function() {
        expect(scope.filters.tenant_tag.length).toBe(4);
      });

      it('should contain filter: RackConnect', function() {
        expect(scope.filters.tenant_tag).toContain({ name: 'RackConnect', active: false });
      });

      it('should contain filter: Managed', function() {
        expect(scope.filters.tenant_tag).toContain({ name: 'Managed', active: false });
      });

      it('should contain filter: Racker', function() {
        expect(scope.filters.tenant_tag).toContain({ name: 'Racker', active: false });
      });

      it('should contain filter: Internal', function() {
        expect(scope.filters.tenant_tag).toContain({ name: 'Internal', active: false });
      });
    });

    describe('when search exists', function() {
      it('should set active flag to true on default search filter', function() {
        $location.search.returns({ tenant_tag: 'Racker' })
        controller = new DeploymentListController(scope, $location, http, resource, scroll, items, navbar, pagination, auth, $q, cmTenant, Deployment, $timeout);
        expect(scope.filters.tenant_tag).toContain({ name: 'Racker', active: true });
      });

      it('should set active flag to true on custom search filters', function() {
        $location.search.returns({ tenant_tag: 'foobar' })
        controller = new DeploymentListController(scope, $location, http, resource, scroll, items, navbar, pagination, auth, $q, cmTenant, Deployment, $timeout);
        expect(scope.filters.tenant_tag).toContain({ name: 'foobar', active: true });
      });
    });
  });

  describe('#applyFilters', function() {
    it('should cancel pending filter promise', function() {
      scope.filter_promise = 'old promise';
      scope.applyFilters();
      expect(scope.filter_promise).not.toEqual('old promise');
    });

    it('should set promise to apply filters', function() {
      scope.applyFilters();
      expect($timeout).toHaveBeenCalledWith(scope.filter_deployments, 1500);
    });

    it('should save promise for future reference', function() {
      scope.filter_promise = null;
      scope.applyFilters();
      expect(scope.filter_promise).toEqual('fake promise');
    });
  });

  describe('#filter_deployments', function() {
    it('should default to setting location to new empty search', function() {
      scope.filter_deployments();
      expect($location.search).toHaveBeenCalledWith({});
    });

    it('should filter by status', function() {
      scope.filter_list = [ { name: 'foobar', active: true } ];
      scope.filter_deployments();
      expect($location.search).toHaveBeenCalledWith({ status: ['foobar'] });
    });

    it('should filter by several statuses at once', function() {
      scope.filter_list = [
        { name: 'foobar', active: true },
        { name: 'mordor', active: true },
      ];
      scope.filter_deployments();
      expect($location.search).toHaveBeenCalledWith({ status: ['foobar', 'mordor'] });
    });

    it('should filter by tenant tag', function() {
      scope.filters.tenant_tag = [ { name: 'foobar', active: true } ];
      scope.filter_deployments();
      expect($location.search).toHaveBeenCalledWith({ tenant_tag: ['foobar'] });
    });

    it('should filter by several active tenant tags at once', function() {
      scope.filters.tenant_tag = [
        { name: 'foobar', active: true },
        { name: 'middle earth', active: false },
        { name: 'mordor', active: true },
      ];
      scope.filter_deployments();
      expect($location.search).toHaveBeenCalledWith({ tenant_tag: ['foobar', 'mordor'] });
    });

    it('should filter by custom search', function() {
      scope.query = 'fake query';
      scope.filter_deployments();
      expect($location.search).toHaveBeenCalledWith({ search: 'fake query' });
    });
  });

  describe('#has_pending_results', function() {
    it('should return true if page not loaded', function() {
      delete scope.items
      expect(scope.has_pending_results()).toBeTruthy();
    });

    it('should return true if there is a promise to filter deployments', function() {
      scope.items = 'fake items';
      scope.filter_promise = 'items will arrive';
      expect(scope.has_pending_results()).toBeTruthy();
    });

    it('should return false if no pending results are available', function() {
      scope.items = 'fake items';
      scope.filter_promise = null;
      expect(scope.has_pending_results()).toBeFalsy();
    });
  });

  describe('error_message', function() {
    it('should default to null', function() {
      expect(scope.error_message).toBe(null);
    });
  });

  describe('#no_results_found', function() {
    it('should return false if there are pending results', function() {
      scope.has_pending_results = sinon.stub().returns(true);
      expect(scope.no_results_found()).toBeFalsy();
    });

    describe('if no pending results are left', function() {
      beforeEach(function() {
        scope.has_pending_results = sinon.stub().returns(false);
      });

      it('should return false if there is an error message', function() {
        scope.error_message = 'foobar';
        expect(scope.no_results_found()).toBeFalsy();
      });

      it('should return true if there are no deployments to be displayed', function() {
        empty_filter = sinon.stub().returns([]);
        $filter.returns(empty_filter);
        expect(scope.no_results_found()).toBeTruthy();
      });

      it('should return false if there are deployments to be displayed', function() {
        some_filter = sinon.stub().returns([1,2,3]);
        $filter.returns(some_filter);
        expect(scope.no_results_found()).toBeFalsy();
      });
    });
  });
});
