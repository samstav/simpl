describe('ResourcesController', function(){
  var $scope,
      $resource,
      $location,
      Deployment;

  beforeEach(function(){
    $scope = {};
    $resource = sinon.stub().returns(emptyFunction);
    $location = {path: sinon.spy()};
    Deployment = {sync: emptyFunction}
    controller = new ResourcesController($scope, $resource, $location, Deployment);
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

  describe('#submit', function(){
    it('should redirect to the new deployment page after submission', function(){
      var data = {'id': '111'}
      var save_spy = sinon.spy();
      $scope.auth = {context: {tenantId: '123'}};
      $scope.get_new_deployment = sinon.stub().returns({$save: save_spy})
      $scope.submit();

      var success_callback = save_spy.getCall(0).args[0]
      success_callback(data)
      expect($location.path.getCall(0).args[0]).toEqual('/123/deployments/111');
    });
  });
});
