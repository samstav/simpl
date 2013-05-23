describe('DeploymentListController', function(){
  var scope,
      location,
      http,
      resource,
      scroll,
      items,
      navbar,
      controller,
      emptyResponse;

  beforeEach(function(){
    scope = { $watch: emptyFunction, auth: { context: {}} };
    location = { search: sinon.stub().returns({}), replace: emptyFunction };
    http = {};
    resource = sinon.stub().returns(emptyResponse);
    scroll = {};
    items = {};
    navbar = { highlight: emptyFunction };
    pagination = { buildPaginator: sinon.stub().returns({ buildPagingParams: sinon.stub().returns('') }) };
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

        expect(resource_spy.getCall(0).args[0]).toEqual('/:tenantId/deployments.json');
        expect(get_spy.getCall(0).args[0]).toEqual({ tenantId: 'cats' });
      });

      it('should append pagination params to the resource call', function(){
        pagination = { buildPaginator: sinon.stub().returns({ buildPagingParams: sinon.stub().returns('?offset=20&limit=30') }) };
        location = { search: sinon.stub().returns({ offset: 20, limit: 30 }), replace: emptyFunction };
        resource = function(){ return { get: emptyFunction }; };
        resource_spy = sinon.spy(resource);
        pagination.extractPagingParams = sinon.stub().returns('?offset=20&limit=30');

        controller = new DeploymentListController(scope, location, http, resource_spy, scroll, items, navbar, pagination);
        expect(resource_spy.getCall(0).args[0]).toEqual('/:tenantId/deployments.json?offset=20&limit=30');
      });
    });
  });
});
