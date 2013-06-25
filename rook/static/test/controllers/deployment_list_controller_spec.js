describe('DeploymentListController', function(){
  var scope,
      location,
      http,
      resource,
      scroll,
      items,
      navbar,
      pagination,
      controller,
      emptyResponse;

  beforeEach(function(){
    scope = { $watch: emptyFunction, auth: { context: {}} };
    location = { search: sinon.stub().returns({}), replace: emptyFunction, path: sinon.stub().returns('/1/deployments') };
    http = {};
    resource = sinon.stub().returns(emptyResponse);
    scroll = {};
    items = {};
    navbar = { highlight: emptyFunction };
    pagination = { buildPaginator: sinon.stub().returns({ changed_params: sinon.spy() }) };
    controller = {};
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

        scope = { $watch: emptyFunction, auth: { context: { tenantId: 'cats' }} };
        controller = new DeploymentListController(scope, location, http, resource_spy, scroll, items, navbar, pagination);
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

        controller = new DeploymentListController(scope, location, http, resource_spy, scroll, items, navbar, pagination);
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

        controller = new DeploymentListController(scope, location, http, resource_spy, scroll, items, navbar, pagination);
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

        controller = new DeploymentListController(scope, location, http, resource_spy, scroll, items, navbar, pagination);
        scope.load();
        expect(resource_spy.getCall(0).args[0]).toEqual('/123/deployments.json');
        expect(get_spy.getCall(0).args[0].show_deleted).toEqual(true);
        expect(get_spy.getCall(0).args[0].cats).toEqual('dogs');
      });
    });
  });
});
