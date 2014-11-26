describe('StaticController', function(){
  var $scope,
      $location,
      controller;
  beforeEach(function() {
    $scope = {};
    $location = { path: emptyFunction };
    controller = new StaticController($scope, $location);
  });

  it('should not display the header', function(){
    expect($scope.showHeader).toBeFalsy();
  });

  it('should not display status', function(){
    expect($scope.showStatus).toBeFalsy();
  });

  it('should set carousel interval to negative number', function() {
    expect($scope.carousel_interval).toBeLessThan(0);
  });

  it('should set spot write URL', function() {
    expect($scope.spot_write_url).toEqual('https://one.rackspace.com/display/Checkmate/Checkmate+Blueprints+Introduction');
  });

  it('should set item base URL', function() {
    expect($scope.item_base_url).toEqual('/deployments/new?blueprint=https:%2F%2Fgithub.rackspace.com%2FBlueprints%2F');
  });

  describe('slides', function() {
    it('should have 5 item sets', function() {
      expect($scope.slides.length).toBe(5);
    });

    it('should contain 4 items in each set', function() {
      expect($scope.slides[0].length).toBe(4);
    });
  });

  describe('#display_name', function() {
    var item;
    beforeEach(function() {
      item = { show_name: true, name: "fakename" }
    });

    it('should return item name if show_name is true', function() {
      expect($scope.display_name(item)).toBe("fakename");
    });

    it('should return null if show_name if false', function() {
      item.show_name = false;
      expect($scope.display_name(item)).toBe(null);
    });
  });

  describe('#in_spot', function() {
    var item;
    beforeEach(function() {
      item = { spot: 'fakespot' };
    });

    it('should return true if item is in spot', function() {
      expect($scope.in_spot(item, 'fakespot')).toBe(true);
    });

    it('should return false if item is not in spot', function() {
      expect($scope.in_spot(item, 'anotherspot')).toBe(false);
    });

    it('should take variable number of spots and still return true', function() {
      expect($scope.in_spot(item, 'anotherspot', 'fakespot')).toBe(true);
    });

    it('should take variable number of spots and still return false', function() {
      expect($scope.in_spot(item, 'anotherspot', 'truespot')).toBe(false);
    });
  });
});

