describe('WorkflowController', function(){
  var controller,
      $scope,
      $resource,
      $http,
      $routeParams,
      $location,
      $window,
      auth,
      workflow,
      items,
      scroll,
      deploymentDataParser;

  beforeEach(function(){
    $scope = { loginPrompt: sinon.stub().returns({ then: emptyFunction }) };
    $resource = {};
    $http = {};
    $routeParams = {};
    $location = {};
    $window = {};
    auth = { identity: {} };
    workflow = {};
    items = {};
    scroll = {};
    controller = new WorkflowController($scope, $resource, $http, $routeParams, $location, $window, auth, workflow, items, scroll, deploymentDataParser);
  });

  it('should show status', function(){
    expect($scope.showStatus).toBe(true);
  });

  it('should show header', function(){
    expect($scope.showHeader).toBe(true);
  });

  it('should show search', function(){
    expect($scope.showSearch).toBe(true);
  });

  it('should show controls', function(){
    expect($scope.showControls).toBe(true);
  });

  describe('shouldDisplayWorkflowStatus', function(){
    describe('operation is a workflow operation', function(){
      beforeEach(function(){
        $scope.$parent = { data:
          { operation:
            { link: '/111/workflows/some_id' }
          }
        };
      });

      it('should return true if status is in progress', function(){
        $scope.$parent.data.operation.status = 'IN PROGRESS';
        controller = new WorkflowController($scope, $resource, $http, $routeParams, $location, $window, auth, workflow, items, scroll, deploymentDataParser);
        expect($scope.shouldDisplayWorkflowStatus()).toBe(true);
      });

      it('should return true if status is paused', function(){
        $scope.$parent.data.operation.status = 'PAUSED';
        controller = new WorkflowController($scope, $resource, $http, $routeParams, $location, $window, auth, workflow, items, scroll, deploymentDataParser);
        expect($scope.shouldDisplayWorkflowStatus()).toBe(true);
      });

      it('should return false if status is not in progress or paused', function(){
        $scope.$parent.data.operation.status = 'DELETED';
        controller = new WorkflowController($scope, $resource, $http, $routeParams, $location, $window, auth, workflow, items, scroll, deploymentDataParser);
        expect($scope.shouldDisplayWorkflowStatus()).toBe(false);
      });
    });

    describe('operation is not a workflow operation', function(){
      it('should return false', function(){
        $scope.$parent = { data:
          { operation:
            { link: '/111/canvases/some_id' }
          }
        };
        controller = new WorkflowController($scope, $resource, $http, $routeParams, $location, $window, auth, workflow, items, scroll, deploymentDataParser);
        expect($scope.shouldDisplayWorkflowStatus()).toBe(false);
      });
    });
  });

  describe('logged in, resource.get callback in #load', function(){
    beforeEach(function(){
      items = {};
      auth.identity = { loggedIn: true };
      $resource = sinon.stub().returns({ get: emptyFunction });
      $location = { path: sinon.stub().returns('/status') };
      workflow = { flattenTasks: sinon.stub().returns([]),
                   parseTasks: sinon.stub().returns([]),
                   calculateStatistics: emptyFunction };
    });

    it('setup all data', function(){
      var data = { wf_spec: ['cat'] };
      var get_spy = sinon.spy();
      $resource = sinon.stub().returns({ get: get_spy });
      controller = new WorkflowController($scope, $resource, $http, $routeParams, $location, $window, auth, workflow, items, scroll, deploymentDataParser);
      var callback = get_spy.getCall(0).args[1];
      callback(data, emptyFunction);
    });
  });

  describe('#toggle_task_traceback', function() {
    it('should togle hide_task_traceback for a given task type to true', function() {
      $scope.hide_task_traceback = { foo: false };
      $scope.toggle_task_traceback('foo');
      expect($scope.hide_task_traceback.foo).toBe(true);
    });

    it('should toggle hide_task_traceback for a given task type to false', function() {
      $scope.hide_task_traceback = { foo: true };
      $scope.toggle_task_traceback('foo');
      expect($scope.hide_task_traceback.foo).toBe(false);
    });
  });
});
