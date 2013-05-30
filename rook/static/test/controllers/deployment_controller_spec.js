describe('DeploymentController', function(){
  var scope,
      location,
      resource,
      routeParams,
      dialog,
      deploymentDataParser,
      controller;

  beforeEach(function(){
    scope = {};
    location = { path: emptyFunction };
    resource = sinon.stub().returns({ get: emptyFunction });
    routeParams = undefined;
    dialog = undefined;
    deploymentDataParser = { formatData: emptyFunction };
    controller = undefined;
  });

  it('should show summaries', function(){
    controller = new DeploymentController(scope, location, resource, routeParams, dialog, deploymentDataParser);
    expect(scope.showSummaries).toBe(true);
  });

  it('should not show status', function(){
    controller = new DeploymentController(scope, location, resource, routeParams, dialog, deploymentDataParser);
    expect(scope.showStatus).toBe(false);
  });

  it('should not show advanced details by default', function(){
    controller = new DeploymentController(scope, location, resource, routeParams, dialog, deploymentDataParser);
    expect(scope.showAdvancedDetails).toBe(false);
  });

  it('should not show instructions by default', function(){
    controller = new DeploymentController(scope, location, resource, routeParams, dialog, deploymentDataParser);
    expect(scope.showInstructions).toBe(false);
  });

  it('should auto refresh', function(){
    controller = new DeploymentController(scope, location, resource, routeParams, dialog, deploymentDataParser);
    expect(scope.auto_refresh).toBe(true);
  });

  it('should set name to Deployment', function(){
    controller = new DeploymentController(scope, location, resource, routeParams, dialog, deploymentDataParser);
    expect(scope.name).toEqual('Deployment');
  });

  describe('load', function(){
    it('should get the resource', function(){
      var resource_result = { get: sinon.spy() };
      resource = sinon.stub().returns(resource_result);
      controller = new DeploymentController(scope, location, resource, routeParams, dialog, deploymentDataParser);
      expect(resource_result.get).toHaveBeenCalled();
    });

    describe('resource.get callback', function(){
      it('should store returned data', function(){
        var data = { cats: 'dogs' },
            resource_result = { get: sinon.spy() };

        resource = sinon.stub().returns(resource_result);
        controller = new DeploymentController(scope, location, resource, routeParams, dialog, deploymentDataParser);
        var callback = resource_result.get.getCall(0).args[1];
        callback(data, emptyFunction);
        expect(scope.data).toEqual(data);
      });

      it('should format data', function(){
        var resource_result = { get: sinon.spy() },
            data = { yeeaaa: 1 };
            deploymentDataParser = { formatData: sinon.stub().returns(data) };

        resource = sinon.stub().returns(resource_result);
        controller = new DeploymentController(scope, location, resource, routeParams, dialog, deploymentDataParser);
        var callback = resource_result.get.getCall(0).args[1];
        callback({}, emptyFunction);
        expect(scope.formatted_data).toEqual(data);
      });
    });
  });
});
