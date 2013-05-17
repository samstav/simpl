describe('loadingInterceptor', function(){

  var request, response, endpoint, user;
  beforeEach(module('checkmate.services'));
  beforeEach(inject(function(loadingInterceptor, $q, $window, $rootScope){
    this.interceptor = loadingInterceptor;
  }));

  it('should instantiate loadingInterceptor', function(){
    expect(this.interceptor).not.toBe(null);
  });

  it('should catch $http promises and pass them along', function() {
    var promise = { then: jasmine.createSpy('then') };
    this.interceptor(promise);
    expect(promise.then).toHaveBeenCalled();
  });

});
