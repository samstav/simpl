describe('auth Service', function(){

  beforeEach(module('checkmate.services'));
  beforeEach(inject(function(auth, $resource, $rootScope){
    this.auth = auth;
  }));

  it('should create an identity object based on request, response, and endpoint', function(){
    request = { getResponseHeader: emptyFunction };
    response = { access: { user: emptyFunction, token: emptyFunction } };
    endpoint = {};
    expect(this.auth.create_identity(request, response, endpoint)).not.toBe(null);
  });

});
