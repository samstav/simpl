describe('ResourcesController', function(){
  var $scope,
      $resource;

  beforeEach(function(){
    $scope = {};
    $resource = {};
    controller = new ResourcesController($scope, $resource);
  });

  it('should setup selected_resources', function(){
    expect($scope.selected_resources).toEqual([]);
  });

  describe('#add_to_deployment', function(){
    it('should add the resource to the selected_resources list', function(){
      var provider = {provider: 'nova'};
      $scope.resources_by_provider['nova'] = [provider];
      $scope.add_to_deployment(provider);
      expect($scope.selected_resources).toEqual([provider]);
    });

    it('should remove the resource from the provider resource list', function(){
      var provider = {provider: 'nova'};
      $scope.resources_by_provider['nova'] = [provider];
      $scope.add_to_deployment(provider);
      expect($scope.resources_by_provider['nova']).toEqual([]);
    });
  });

  describe('#remove_from_deployment', function(){
    it('should remove the resource from selected_resources', function(){
      var provider = {provider: 'nova'};
      $scope.selected_resources = [provider];
      $scope.remove_from_deployment(provider);
      expect($scope.selected_resources).toEqual([]);
    });

    it('should add the resource to the provider resource list', function(){
      var provider = {provider: 'nova'};
      $scope.selected_resources = [provider];
      $scope.remove_from_deployment(provider);
      expect($scope.resources_by_provider['nova']).toEqual([provider]);
    });
  });
});
