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
    location = { search: sinon.stub().returns({}) };
    http = {};
    resource = sinon.stub().returns(emptyResponse);
    scroll = {};
    items = {};
    navbar = { highlight: emptyFunction };
    controller = {};
    emptyResponse = { get: emptyFunction };
  });

  describe('initialization', function(){
    describe('load', function(){
      var get_spy,
          resource_spy;

      it('should setup the url and get the resource with the tenantId', function(){
        get_spy = sinon.spy();
        resource = function(){ return { get: get_spy }; };
        resource_spy = sinon.spy(resource);

        scope = { $watch: emptyFunction, auth: { context: { tenantId: 'cats' }} };
        controller = new DeploymentListController(scope, location, http, resource_spy, scroll, items, navbar);

        expect(resource_spy.getCall(0).args[0]).toEqual('/:tenantId/deployments.json');
        expect(get_spy.getCall(0).args[0]).toEqual({ tenantId: 'cats' });
      });

      it('should append pagination params to the resource call', function(){
        location = { search: sinon.stub().returns({ offset: 20, limit: 30 }) };
        resource = function(){ return { get: emptyFunction }; };
        resource_spy = sinon.spy(resource);

        controller = new DeploymentListController(scope, location, http, resource_spy, scroll, items, navbar);
        expect(resource_spy.getCall(0).args[0]).toEqual('/:tenantId/deployments.json?offset=20&limit=30');
      });

      it('should not append non-pagination params to the resource call', function(){
        location = { search: sinon.stub().returns({ pizza: 'cat', deadpool: 'spiderpig' }) };
        resource = function(){ return { get: emptyFunction }; };
        resource_spy = sinon.spy(resource);

        controller = new DeploymentListController(scope, location, http, resource_spy, scroll, items, navbar);
        expect(resource_spy.getCall(0).args[0]).toEqual('/:tenantId/deployments.json');
      });
    });
  });
});
