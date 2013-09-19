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
      var provider = { object: {provider: 'nova'} };
      $scope.resources_by_provider['nova'] = [provider];
      $scope.add_to_deployment(provider);
      expect($scope.selected_resources).toEqual([provider]);
    });

    it('should remove the resource from the provider resource list', function(){
      var provider = { object: {provider: 'nova'} };
      $scope.resources_by_provider['nova'] = [provider];
      $scope.add_to_deployment(provider);
      expect($scope.resources_by_provider['nova']).toEqual([]);
    });
  });

  describe('#remove_from_deployment', function(){
    it('should remove the resource from selected_resources', function(){
      var provider = { object: {provider: 'nova'} };
      $scope.selected_resources = [provider];
      $scope.resources_by_provider['nova'] = [];
      $scope.remove_from_deployment(provider);
      expect($scope.selected_resources).toEqual([]);
    });

    it('should add the resource to the provider resource list', function(){
      var provider = { object: {provider: 'nova'} };
      $scope.selected_resources = [provider];
      $scope.resources_by_provider['nova'] = [];
      $scope.remove_from_deployment(provider);
      expect($scope.resources_by_provider['nova']).toEqual([provider]);
    });
  });

  describe('#submit', function(){
    var data, mock_deployment;
    beforeEach(function() {
      data = {'id': '111'}
      mock_deployment = {$save: emptyFunction}
      $scope.auth = {context: {tenantId: '123'}};
      $scope.deployment = {name: 'deadpool'}
      $scope.get_new_deployment = sinon.stub().returns(mock_deployment)
    })

    it('should redirect to the new deployment page after submission', function(){
      var save_spy = sinon.spy();
      $scope.get_new_deployment = sinon.stub().returns({$save: save_spy})
      $scope.submit();

      var success_callback = save_spy.getCall(0).args[0]
      success_callback(data)
      expect($location.path.getCall(0).args[0]).toEqual('/123/deployments/111');
    });

    it('should set the status of a new deployment to NEW', function() {
      $scope.submit();
      expect(mock_deployment.status).toEqual('NEW')
    });

    it('should add an array of custom resources to deployment', function() {
      $scope.selected_resources = [{object: {id: 'r1'}}, {object: {id: 'r2'}}];
      $scope.submit();
      expect(mock_deployment.inputs.custom_resources).toContain({id: 'r1'})
      expect(mock_deployment.inputs.custom_resources).toContain({id: 'r2'})
    });

    describe('- blueprint', function() {
      beforeEach(function() {
        $scope.submit();
      });

      it('should add services', function() {
        expect(mock_deployment.blueprint.services).toEqual({})
      });

      it('should add information for Reach to display in the deployment', function() {
        expect(mock_deployment.blueprint.name).toEqual('deadpool');
        expect(mock_deployment.blueprint['meta-data']).toEqual({'application-name': 'Custom'})
      });
    });

    describe('- deployment environment', function() {
      beforeEach(function() {
        $scope.submit();
      });

      it('should add a description', function() {
        var expected = 'This environment uses next-gen cloud servers.';
        expect(mock_deployment.environment.description).toEqual(expected)
      });

      it('should add a name', function() {
        var expected = 'Next-Gen Open Cloud';
        expect(mock_deployment.environment.name).toEqual(expected)
      });

      it('shoud add providers', function() {
        var expected = 'Next-Gen Open Cloud';
        expect(mock_deployment.environment.providers.nova).toEqual({})
        expect(mock_deployment.environment.providers.database).toEqual({})
        expect(mock_deployment.environment.providers['load-balancer']).toEqual({})
        expect(mock_deployment.environment.providers.common).toEqual({vendor: 'rackspace'})
      });
    });
  });
});
