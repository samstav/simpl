describe('RawController', function(){
  var scope, location, http, stubbed_callbacks;
  beforeEach(function() {
    http = emptyFunction;
    scope = {};
    location = { absUrl: emptyFunction };
  });

  it('should not display the header', function(){
    stubbed_callbacks = { success: sinon.stub().returns( { error: emptyFunction } ) };
    http = sinon.stub().returns(stubbed_callbacks);
    controller = new RawController(scope, location, http);
    expect(scope.showHeader).toBeFalse;
  });

  it('should not display status', function(){
    stubbed_callbacks = { success: sinon.stub().returns( { error: emptyFunction } ) };
    http = sinon.stub().returns(stubbed_callbacks);
    controller = new RawController(scope, location, http);
    expect(scope.showStatus).toBeFalse;
  });

  it('should perform a get on the location abs url', function(){
    stubbed_callbacks = { success: sinon.stub().returns( { error: emptyFunction } ) };
    http = sinon.stub().returns(stubbed_callbacks);
    location.absUrl = function(){ return 'absUrl'; };
    sinon.spy(http);
    controller = new RawController(scope, location, http);
    expect(http).toHaveBeenCalledWith({ method: 'GET', url: 'absUrl' });
  });
});
