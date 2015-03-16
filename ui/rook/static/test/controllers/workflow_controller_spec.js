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
      scroll,
      deploymentDataParser,
      $timeout,
      $q,
      urlBuilder;

  beforeEach(function(){
    $scope = { loginPrompt: sinon.stub().returns({ then: emptyFunction }), '$watch': emptyFunction, '$on': sinon.spy() };
    $resource = {};
    $http = {};
    $routeParams = {};
    $location = {};
    $window = {};
    auth = { identity: {} };
    workflow = { flattenTasks: emptyFunction };
    scroll = {};
    $timeout = {};
    $q = { defer: sinon.stub().returns({ resolve: emptyFunction, promise: {} }) };
    urlBuilder = {};
    controller = new WorkflowController($scope, $resource, $http, $routeParams, $location, $window, auth, workflow, scroll, deploymentDataParser, $timeout, $q, urlBuilder);
  });

  it('should show status', function(){
    expect($scope.showStatus).toBe(true);
  });

  it('should show search', function(){
    expect($scope.showSearch).toBe(true);
  });

  it('should show controls', function(){
    expect($scope.showControls).toBe(true);
  });

  describe('logged in, resource.get callback in #load', function(){
    beforeEach(function(){
      auth.identity = { loggedIn: true };
      $resource = sinon.stub().returns({ get: emptyFunction });
      $location = { path: sinon.stub().returns('/status') };
      workflow = { flattenTasks: sinon.stub().returns([]),
                   parseTasks: sinon.stub().returns([]),
                   calculateStatistics: sinon.stub().returns({ taskStates: {} }) };
    });

    it('setup all data', function(){
      var data = { wf_spec: ['cat'] };
      var get_spy = sinon.spy();
      $resource = sinon.stub().returns({ get: get_spy });
      controller = new WorkflowController($scope, $resource, $http, $routeParams, $location, $window, auth, workflow, scroll, deploymentDataParser, $timeout, $q, urlBuilder);
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

  describe('#workflow_action_success', function() {
    beforeEach(function() {
      var response = { config: { url: '/fakeurl/+fakeaction' } };
      $location.path = sinon.stub().returns('/fakeurl');
      $scope.notify = sinon.stub();
      spyOn($scope, 'load');
      $scope.workflow_action_success(response);
    });

    it('should notify action was successfull', function() {
      expect($scope.notify).toHaveBeenCalledWith("Command 'fakeaction' workflow executed");
    });

    it('should reload scope', function() {
      expect($scope.load).toHaveBeenCalled();
    });
  });

  describe('#workflow_action_error', function() {
    var response;
    beforeEach(function() {
      response = { config: { url: '/fakeurl/+fakeaction' } };
      $location.path = sinon.stub().returns('/fakeurl');
      $scope.notify = sinon.stub();
      $scope.show_error = sinon.spy();
      $scope.workflow_action_error(response);
    });

    it('should display the error modal dialog', function() {
      expect($scope.show_error).toHaveBeenCalledWith(response);
    });
  });

  describe('#workflow_action', function() {
    it('should display login prompt if not logged in', function() {
      auth.identity.loggedIn = false;
      spyOn($scope, 'loginPrompt').andReturn({ then: emptyFunction });
      $scope.workflow_action('fakeid', 'fakeaction');
      expect($scope.loginPrompt).toHaveBeenCalled();
    });

    describe('if logged in', function() {
      var $rootScope, $q, deferred;
      beforeEach(inject(function($injector) {
        $q = $injector.get('$q');
        $rootScope = $injector.get('$rootScope');
        deferred = $q.defer();
        auth.identity.loggedIn = true;
        $http.get = sinon.stub().returns(deferred.promise);
        $location.path = sinon.stub().returns('/fakepath');
        spyOn(console, 'log');
        spyOn($scope, 'workflow_action_success');
        spyOn($scope, 'workflow_action_error');
        $scope.workflow_action('fakeid', 'fakeaction');
      }));

      it('should log action to console ', function() {
        expect(console.log).toHaveBeenCalled();
      });

      it('should submit action to server', function() {
        expect($http.get).toHaveBeenCalledWith('/fakepath/+fakeaction');
      });

      it('should call workflow_action_success if action is successfull', function() {
        deferred.resolve('success');
        $rootScope.$apply();
        expect($scope.workflow_action_success).toHaveBeenCalled();
      });

      it('should call workflow_action_error if action is not successfull', function() {
        deferred.reject('error');
        $rootScope.$apply();
        expect($scope.workflow_action_error).toHaveBeenCalled();
      });
    });
  });

  describe('#is_paused', function() {
    beforeEach(function() {
      $scope.data = { attributes: { status: 'fakestatus' } };
    });

    it('should be false if there is no data available', function() {
      $scope.data = undefined;
      expect($scope.is_paused()).toBeFalsy();
    });

    it('should be false if status is not "PAUSED"', function() {
      expect($scope.is_paused()).toBe(false);
    });

    it('should be true if status is "PAUSED"', function() {
      $scope.data.attributes.status = "PAUSED";
      expect($scope.is_paused()).toBe(true);
    });
  });

  describe('#selectTask', function(){
    beforeEach(function(){
      $scope.data = { task_tree: 'irrelevant' };
    });

    it('should set the current task index', function(){
      $scope.selectTask(1);
      expect($scope.current_task_index).toEqual(1);
    });
  });

  describe('#resource', function(){
    it('should find the resource in the workflow task based off the spec property', function(){
      var resource = {'a': 'resource'};
      var spec = {'properties': {'resource': '1'}};
      var task = {'attributes': {'instance:0': 'something else', 'instance:1': resource}};
      expect($scope.resource(task, spec)).toEqual(resource);
    });

    it('should return null if no task given', function(){
      var resource = {'a': 'resource'};
      var spec = {'properties': {'resource': '1'}};
      var task = undefined;
      expect($scope.resource(task, spec)).toEqual(null);
    });

    it('should return null if no spec given', function(){
      var resource = {'a': 'resource'};
      var spec = undefined;
      var task = {'attributes': {'instance:0': 'something else', 'instance:1': resource}};
      expect($scope.resource(task, spec)).toEqual(null);
    });
  });
});