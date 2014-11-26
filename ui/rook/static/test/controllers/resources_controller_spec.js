describe('ResourcesController', function(){
  var $scope,
      $resource,
      $location,
      Deployment;

  beforeEach(function(){
    $scope = {};
    $resource = sinon.stub().returns({query: emptyFunction});
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
        var metadata = mock_deployment.blueprint['meta-data']
        var reach_info = metadata['reach-info']
        expect(mock_deployment.blueprint.name).toEqual('deadpool');
        expect(metadata['application-name']).toEqual('Custom')
        expect(reach_info['tattoo']).toEqual('http://7555e8905adb704bd73e-744765205721eed93c384dae790e86aa.r66.cf2.rackcdn.com/custom-tattoo.png')
        expect(reach_info['icon-20x20']).toEqual('http://7555e8905adb704bd73e-744765205721eed93c384dae790e86aa.r66.cf2.rackcdn.com/custom-20x20.png')
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


  describe('getting rackspace api resources', function(){
    beforeEach(function(){
      var auth = {
        context: { tenantId: '123' },
        identity: {loggedIn: true}
      }
      $scope.auth = auth
    });

    describe('#get_resources', function(){
      it('should clear any resource error messages', function(){
        $scope.error_msgs.foobar = "This error shouldnt exist!!!";
        $scope.get_resources('foobar');
        expect($scope.error_msgs.foobar).toBeUndefined();
      });

      it('should set loading status to true', function(){
        $scope.loading_status.foobar = false;
        $scope.get_resources('foobar');
        expect($scope.loading_status.foobar).toBe(true);
      });
    });
  });
});
