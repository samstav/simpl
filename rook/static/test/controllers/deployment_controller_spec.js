describe('DeploymentController', function(){
  var $scope,
      location,
      resource,
      routeParams,
      dialog,
      deploymentDataParser,
      controller;

  beforeEach(function(){
    $scope = {};
    location = { path: emptyFunction, absUrl: emptyFunction };
    resource = sinon.stub().returns({ get: emptyFunction });
    routeParams = undefined;
    dialog = undefined;
    deploymentDataParser = { formatData: emptyFunction };
    controller = new DeploymentController($scope, location, resource, routeParams, dialog, deploymentDataParser);
  });

  it('should show summaries', function(){
    expect($scope.showSummaries).toBe(true);
  });

  it('should not show status', function(){
    expect($scope.showStatus).toBe(false);
  });

  it('should not show advanced details by default', function(){
    expect($scope.showAdvancedDetails).toBe(false);
  });

  it('should not show instructions by default', function(){
    expect($scope.showInstructions).toBe(false);
  });

  it('should auto refresh', function(){
    expect($scope.auto_refresh).toBe(true);
  });

  it('should set name to Deployment', function(){
    expect($scope.name).toEqual('Deployment');
  });

  describe('#load', function() {
    it('should get the resource', function() {
      var resource_result = { get: sinon.spy() };
      resource.returns(resource_result);
      $scope.load();
      expect(resource_result.get).toHaveBeenCalled();
    });

    describe('resource.get callback', function(){
      it('should store returned data', function(){
        var data = { cats: 'dogs' },
            resource_result = { get: sinon.spy() };

        resource.returns(resource_result);
        $scope.load()
        var callback = resource_result.get.getCall(0).args[1];
        callback(data, emptyFunction);
        expect($scope.data).toEqual(data);
      });

      it('should format data', function(){
        var resource_result = { get: sinon.spy() },
            data = { yeeaaa: 1 };
            deploymentDataParser.formatData = sinon.stub().returns(data);

        resource.returns(resource_result);
        $scope.load();
        var callback = resource_result.get.getCall(0).args[1];
        callback({}, emptyFunction);
        expect($scope.formatted_data).toEqual(data);
      });
    });
  });
});
