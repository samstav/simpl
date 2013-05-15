describe('auth Service', function(){

  var request, response, endpoint, user;
  beforeEach(module('checkmate.services'));
  beforeEach(inject(function(auth, $resource, $rootScope){
    this.auth = auth;
    request = { getResponseHeader: emptyFunction };
    user = {};
    response = { access: { user: user, token: emptyFunction } };
    endpoint = {};
  }));

  describe('create_identity', function(){
    it('should create an identity object based on request, response, and endpoint', function(){
      expect(this.auth.create_identity(request, response, endpoint)).not.toBe(null);
    });

    it('should assign is_admin to true if the X-AuthZ-Admin header is True', function(){
      request = { getResponseHeader: function(){ return 'True'; } };
      expect(this.auth.create_identity(request, response, endpoint).is_admin).toBeTruthy();
    });

    it('should assign is_admin to false if the X-AuthZ-Admin header is not "True"', function(){
      request = { getResponseHeader: function(){ return 'Truish'; } };
      expect(this.auth.create_identity(request, response, endpoint).is_admin).toBeFalsy();
    });

    it('should set username to the access user name if it is present', function(){
      user = { name: 'batman' };
      response = { access: { user: user, token: emptyFunction } };
      expect(this.auth.create_identity(request, response, endpoint).username).toEqual('batman');
    });

    it('should set username to the access user id if user name is not present', function(){
      user = { id: 'robin' };
      response = { access: { user: user, token: emptyFunction } };
      expect(this.auth.create_identity(request, response, endpoint).username).toEqual('robin');
    });
  });
});
