describe('WorkflowController', function(){
  var scope,
      resource,
      http,
      routeParams,
      location,
      window,
      workflow,
      items,
      scroll,
      deploymentDataParser,
      controller;

  beforeEach(function(){
    scope = { loginPrompt: emptyFunction, auth: { identity: {} } };
    resource = undefined;
    http = undefined;
    routeParams = undefined;
    location = undefined;
    window = undefined;
    workflow = undefined;
    items = undefined;
    scroll = undefined;
    deploymentDataParser = undefined;
    controller = undefined;
  });

  it('should show status', function(){
    controller = new WorkflowController(scope, resource, http, routeParams, location, window, workflow, items, scroll, deploymentDataParser);
    expect(scope.showStatus).toBe(true);
  });

  it('should show header', function(){
    controller = new WorkflowController(scope, resource, http, routeParams, location, window, workflow, items, scroll, deploymentDataParser);
    expect(scope.showHeader).toBe(true);
  });

  it('should show search', function(){
    controller = new WorkflowController(scope, resource, http, routeParams, location, window, workflow, items, scroll, deploymentDataParser);
    expect(scope.showSearch).toBe(true);
  });

  it('should show controls', function(){
    controller = new WorkflowController(scope, resource, http, routeParams, location, window, workflow, items, scroll, deploymentDataParser);
    expect(scope.showControls).toBe(true);
  });

  describe('logged in, resource.get callback in #load', function(){
    beforeEach(function(){
      items = {};
      scope = { auth: { identity: { loggedIn: true } } };
      resource = sinon.stub().returns({ get: emptyFunction });
      location = { path: sinon.stub().returns('/status') };
      workflow = { flattenTasks: sinon.stub().returns([]),
                   parseTasks: sinon.stub().returns([]),
                   calculateStatistics: emptyFunction };
    });

    it('setup all data', function(){
      var data = { wf_spec: ['cat'] };
      var get_spy = sinon.spy();
      resource = sinon.stub().returns({ get: get_spy });
      controller = new WorkflowController(scope, resource, http, routeParams, location, window, workflow, items, scroll, deploymentDataParser);
      var callback = get_spy.getCall(0).args[1];
      callback(data, emptyFunction);
    });
  });
});
