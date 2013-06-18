describe('WorkflowListController', function(){
  var scope,
      location,
      resource,
      workflow,
      items,
      navbar,
      scroll,
      pagination,
      controller,
      resource_spy,
      emptyResponse;

  beforeEach(function(){
    scope = { $watch: emptyFunction, auth: { context: {}} };
    location = { search: sinon.stub().returns({}), replace: emptyFunction };
    http = {};
    resource = sinon.stub().returns(emptyResponse);
    resource_spy = {};
    scroll = {};
    items = {};
    navbar = { highlight: emptyFunction };
    pagination = { buildPaginator: sinon.stub().returns({ buildPagingParams: sinon.stub().returns(''), changed_params: sinon.spy() }) };
    controller = {};
    emptyResponse = { get: emptyFunction };
  });

  describe('initialization', function(){
    describe('load', function(){
      it('should setup the url and get the resource with the tenantId', function(){
        get_spy = sinon.spy();
        resource = function(){ return { get: get_spy }; };
        resource_spy = sinon.spy(resource);

        scope = { $watch: emptyFunction, auth: { context: { tenantId: 'cats' }} };
        controller = new WorkflowListController(scope, location, resource_spy, workflow, items, navbar, scroll, pagination);
        scope.load();

        expect(resource_spy.getCall(0).args[0]).toEqual('/:tenantId/workflows.json');
        expect(get_spy.getCall(0).args[0]).toEqual({ tenantId: 'cats' });
      });

      it('should append pagination params to the resource call', function(){
        pagination.buildPaginator().buildPagingParams.returns('?offset=20&limit=30');
        location = { search: sinon.stub().returns({ offset: 20, limit: 30 }), replace: emptyFunction };
        resource = function(){ return { get: emptyFunction }; };
        resource_spy = sinon.spy(resource);
        pagination.extractPagingParams = sinon.stub().returns('?offset=20&limit=30');

        controller = new WorkflowListController(scope, location, resource_spy, workflow, items, navbar, scroll, pagination);
        scope.load();
        expect(resource_spy.getCall(0).args[0]).toEqual('/:tenantId/workflows.json?offset=20&limit=30');
      });
    });
  });
});
