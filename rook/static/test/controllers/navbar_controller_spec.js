describe('NavBarController', function(){
  var $scope,
      $location,
      $http,
      controller;

  beforeEach(function() {
    $scope = { '$apply': emptyFunction, loginPrompt: emptyFunction };
    $location = { path: emptyFunction };
    $http = { pendingRequests: [] };
    controller = new NavBarController($scope, $location, $http);
  });

  describe('#hasPendingRequests', function() {
    it('should detect 0 pending http requests', function() {
      expect($scope.hasPendingRequests()).toBe(false);
    });

    it('should detect 1+ pending http requests', function() {
      $http.pendingRequests = [1,2,3]
      expect($scope.hasPendingRequests()).toBe(true);
    });
  });

  it('should collapse navbar by default', function() {
    expect($scope.collapse_navbar).toBe(true);
  });

  describe('#toggle_navbar', function() {
    it('should collapse navbar if not collapsed', function() {
      $scope.collapse_navbar = false;
      $scope.toggle_navbar();
      expect($scope.collapse_navbar).toBe(true);
    });

    it('should display navbar if collapsed', function() {
      $scope.collapse_navbar = true;
      $scope.toggle_navbar();
      expect($scope.collapse_navbar).toBe(false);
    });
  });
});
