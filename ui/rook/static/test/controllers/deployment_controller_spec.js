describe('DeploymentController', function(){
  var $scope,
      location,
      resource,
      routeParams,
      dialog,
      deploymentDataParser,
      $http,
      urlBuilder,
      controller,
      Deployment,
      workflow;

  beforeEach(function(){
    $scope = { $watch: sinon.spy(), auth: { is_current_tenant: sinon.stub() } };
    location = { path: emptyFunction, absUrl: emptyFunction };
    resource = sinon.stub().returns({ get: emptyFunction });
    routeParams = undefined;
    dialog = undefined;
    deploymentDataParser = { formatData: emptyFunction };
    $http = { post: sinon.spy() };
    urlBuilder = {};
    Deployment = { status: emptyFunction };
    controller = new DeploymentController($scope, location, resource, routeParams, dialog, deploymentDataParser, $http, urlBuilder, Deployment, workflow);
    workflow = {};
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

  describe('#get_blueprint_url', function() {
    var deployment, constraint;
    beforeEach(function() {
      constraint = { source: "" };
      deployment = { environment: { providers: { example: { constraints: [ constraint ] } } } };
    });

    it("should return empty string if deployment is not ready or doesn't have URL", function() {
      deployment = undefined;
      expect($scope.get_blueprint_url(deployment)).toEqual("");
      deployment = {};
      expect($scope.get_blueprint_url(deployment)).toEqual("");
      deployment.environment = {};
      expect($scope.get_blueprint_url(deployment)).toEqual("");
      deployment.environment.providers = {};
      expect($scope.get_blueprint_url(deployment)).toEqual("");
      deployment.environment.providers.example = {};
      expect($scope.get_blueprint_url(deployment)).toEqual("");
      deployment.environment.providers.example.constraints = [];
      expect($scope.get_blueprint_url(deployment)).toEqual("");
    });

    it("should replace git:// protocol with http://", function() {
      constraint.source = "git://asdf.com/repo";
      expect($scope.get_blueprint_url(deployment)).toEqual("http://asdf.com/repo");
    });

    it("should replace .git repo format at the end with an empty string", function() {
      constraint.source = "git://asdf.com/repo.git";
      expect($scope.get_blueprint_url(deployment)).toEqual("http://asdf.com/repo");
    });

    it("should replace protocol and repo format even with branches", function() {
      constraint.source = "git://asdf.com/repo.git#stable";
      expect($scope.get_blueprint_url(deployment)).toEqual("http://asdf.com/repo#stable");
    });

    it("should not replace random .git in the middle of the url", function() {
      constraint.source = "git://asdf.github.com/repo.git#stable";
      expect($scope.get_blueprint_url(deployment)).toEqual("http://asdf.github.com/repo#stable");
    });
  });

  describe('#display_details', function() {
    it("should return true if there are details to be displayed", function() {
      var details = { d1: { info: 'valuable!' } };
      expect($scope.display_details(details)).toBe(true);
    });

    it("should return true if it is not secret", function() {
      var details = { d2: { 'is-secret': false }  }
      expect($scope.display_details(details)).toBe(true);
    });

    it("should return true even if there are secrets", function() {
      var details = { d1: { info: 'valuable!' }, d2: { 'is-secret': true }  }
      expect($scope.display_details(details)).toBe(true);
    });

    it("should return false if there are only secrets", function() {
      var details = { d2: { 'is-secret': true }  }
      expect($scope.display_details(details)).toBe(false);
    });

    it("should return false if there is nothing to show", function() {
      var details = {}
      expect($scope.display_details(details)).toBe(false);
    });
  });

  describe('#check', function() {
    var deployment, response, $rootScope;
    beforeEach(inject(function(_$rootScope_, $q) {
      $rootScope = _$rootScope_;
      deployment = {};
      response = $q.defer();
      Deployment.check = sinon.stub().returns(response.promise);
    }));

    it('should set loading status to true', function() {
      $scope.check(deployment);
      expect($scope.loading.check).toBe(true);
    });

    it('should set resource_info to empty object', function() {
      $scope.check(deployment);
      expect($scope.resources_info).toEqual({});
    });

    describe('- successfully loaded', function() {
      var check_response;
      beforeEach(function() {
        $scope.check(deployment);
        check_response = { data: { resources: {} } };
      });

      it('should set loading status to false', function() {
        response.resolve(check_response);
        $rootScope.$apply();
        expect($scope.loading.check).toBe(false);
      });

      it('should group messages to resources_info', function() {
        check_response.data.resources['0'] = [
          {type: 'INFORMATION', message: 'info_msg1'},
          {type: 'ERROR', message: 'error_msg1'},
          {type: 'INFORMATION', message: 'info_msg2'},
        ];
        response.resolve(check_response);
        $rootScope.$apply();
        expect($scope.resources_info['0'].error).toEqual(['error_msg1']);
        expect($scope.resources_info['0'].info).toEqual(['info_msg1', 'info_msg2']);
      });
    });

    describe('- unsuccessfully loaded', function() {
      beforeEach(function() {
        $scope.check(deployment);
        response.reject();
        $rootScope.$apply();
      });

      it('should set loading status to false', function() {
        expect($scope.loading.check).toBe(false);
      });
    });
  });

  describe('#group_resources', function() {
    it('should return an empty group if there are no resources', function() {
      expect($scope.group_resources()).toEqual({});
    });

    it('should group resources by dns-name', function() {
      var resources = {
        0: { 'dns-name': 'dns0', name: 'alpha' },
        1: { 'dns-name': 'dns1', name: 'beta' },
        2: { 'dns-name': 'dns0', name: 'gama' },
        3: { 'dns-name': 'dns1', name: 'delta' },
      };
      var groups = $scope.group_resources(resources);
      expect(groups['dns0']).toContain({'dns-name': 'dns0', name: 'alpha'});
      expect(groups['dns0']).toContain({'dns-name': 'dns0', name: 'gama'});

      expect(groups['dns1']).toContain({'dns-name': 'dns1', name: 'beta'});
      expect(groups['dns1']).toContain({'dns-name': 'dns1', name: 'delta'});
    });
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
        callback(data, emptyFunction);
        expect($scope.formatted_data).toEqual(data);
      });

      it('should not blow up with an error', function(){
        var resource_result = { get: sinon.spy() },
            data = { resources: [{ type: 'load-balancer', instance: null }] };

        deploymentDataParser.formatData = sinon.stub().throws();

        resource.returns(resource_result);
        $scope.load();
        var callback = resource_result.get.getCall(0).args[1];
        expect(function(){ callback(data, emptyFunction) }).not.toThrow();
      });

      it('should showCommands if the data tenantId matches the current user context', function(){
        var data = { tenantId: 12345 },
            resource_result = { get: sinon.spy() };

        resource.returns(resource_result);
        $scope.load()
        $scope.auth.context = { tenantId: 12345 };
        var callback = resource_result.get.getCall(0).args[1];
        callback(data, emptyFunction);
        expect($scope.data).toEqual(data);
      });
    });
  });

  describe('#operation_progress', function() {
    it('should return 0 if operation does not exist', function() {
      expect($scope.operation_progress()).toBe(0);
    });

    describe('for 78 tasks', function() {
      beforeEach(function() {
        $scope.data.operation = { tasks: 78 };
      });

      it('should return 5 if only 4 tasks are complete', function() {
        $scope.data.operation.complete = 4;
        expect($scope.operation_progress()).toBe(5);
      });

      it('should round down to 45 if 35 tasks are complete', function() {
        $scope.data.operation.complete = 35;
        expect($scope.operation_progress()).toBe(45);
      });

      it('should round up to 46 if 36 tasks are complete', function() {
        $scope.data.operation.complete = 36;
        expect($scope.operation_progress()).toBe(46);
      });

      it('should return 100 if all tasks are complete', function() {
        $scope.data.operation.complete = 78;
        expect($scope.operation_progress()).toBe(100);
      });
    });
  });

  describe('#is_resumable', function() {
    it('should return true if operation is resumable', function() {
      $scope.data.operation = { resumable: true };
      expect($scope.is_resumable()).toBeTruthy();
    });

    it('should return false if operation is not resumable', function() {
      $scope.data.operation = { resumable: false };
      expect($scope.is_resumable()).toBeFalsy();
    });

    it('should return false if operation does not contain resume information', function() {
      expect($scope.is_resumable()).toBeFalsy();
    });
  });

  describe('#is_retriable', function() {
    it('should return true if operation is retriable', function() {
      $scope.data.operation = { retriable: true };
      expect($scope.is_retriable()).toBeTruthy();
    });

    it('should return false if operation is not retriable', function() {
      $scope.data.operation = { retriable: false };
      expect($scope.is_retriable()).toBeFalsy();
    });

    it('should return false if operation does not contain retry information', function() {
      expect($scope.is_retriable()).toBeFalsy();
    });
  });

  describe('#retry', function() {
    beforeEach(function() {
      spyOn($http, 'post');
      $scope.data = { id: 'fakeid', operation: { 'retry-link': 'fakelink', 'retriable': true } };
      $scope.retry();
    });

    it('should post to retry-lik', function() {
      expect($http.post).toHaveBeenCalledWith('fakelink');
    });
  });

  describe('#resume', function() {
    beforeEach(function() {
      spyOn($http, 'post');
      $scope.data = { id: 'fakeid', operation: { 'resume-link': 'fakelink', 'resumable': true } };
      $scope.resume();
    });

    it('should post to resume-link', function() {
      expect($http.post).toHaveBeenCalledWith('fakelink');
    });
  });

  describe('shouldDisplayWorkflowStatus', function(){
    describe('operation is a workflow operation', function(){
      beforeEach(function(){
        $scope.data = { operation: { link: '/111/workflows/some_id' } };
      });

      it('should return true if status is in progress', function(){
        controller = new DeploymentController($scope, location, resource, routeParams, dialog, deploymentDataParser, $http, urlBuilder, Deployment, workflow);
        $scope.data = { operation: { link: '/111/workflows/some_id', status: 'IN PROGRESS' } };
        expect($scope.shouldDisplayWorkflowStatus()).toBe(true);
      });

      it('should return true if status is paused', function(){
        controller = new DeploymentController($scope, location, resource, routeParams, dialog, deploymentDataParser, $http, urlBuilder, Deployment, workflow);
        $scope.data = { operation: { link: '/111/workflows/some_id', status: 'PAUSED' } };
        expect($scope.shouldDisplayWorkflowStatus()).toBe(true);
      });

      it('should return true if status is new', function(){
        controller = new DeploymentController($scope, location, resource, routeParams, dialog, deploymentDataParser, $http, urlBuilder, Deployment, workflow);
        $scope.data = { operation: { link: '/111/workflows/some_id', status: 'NEW' } };
        expect($scope.shouldDisplayWorkflowStatus()).toBe(true);
      });

      it('should return false if status is not in progress or paused', function(){
        controller = new DeploymentController($scope, location, resource, routeParams, dialog, deploymentDataParser, $http, urlBuilder, Deployment, workflow);
        $scope.data = { operation: { link: '/111/workflows/some_id', status: 'DELETED' } };
        expect($scope.shouldDisplayWorkflowStatus()).toBe(false);
      });

      it('should return false if there is no operation link such as in deployments created from existing resources', function(){
        controller = new DeploymentController($scope, location, resource, routeParams, dialog, deploymentDataParser, $http, urlBuilder, Deployment, workflow);
        $scope.data = { operation: { status: 'IN PROGRESS' } };
        expect($scope.shouldDisplayWorkflowStatus()).toBe(false);
      });

      it('should return false if there is no status', function(){
        controller = new DeploymentController($scope, location, resource, routeParams, dialog, deploymentDataParser, $http, urlBuilder, Deployment, workflow);
        $scope.data = { operation: { link: '/111/blah' } };
        expect($scope.shouldDisplayWorkflowStatus()).toBe(false);
      });
    });

    describe('operation is not a workflow operation', function(){
      it('should return false', function(){
        controller = new DeploymentController($scope, location, resource, routeParams, dialog, deploymentDataParser, $http, urlBuilder, Deployment, workflow);
        $scope.data = { operation: { link: '/111/canvases/some_id' } };
        expect($scope.shouldDisplayWorkflowStatus()).toBe(false);
      });
    });
  });

  describe('load_workflow_stats', function(){
    var operation;
    beforeEach(function(){
      operation = {};
    });

    it('should not do anything if the operation has canvases in its link', function(){
      operation = { link: '5555/canvases/2saidjfio' };
      controller = new DeploymentController($scope, location, resource, routeParams, dialog, deploymentDataParser, $http, urlBuilder, Deployment, workflow);
      $scope.load_workflow_stats(operation);
      expect(resource).not.toHaveBeenCalled();
    });

    it('should not do anything if the operation does not have a link such as deployments created from existing resources', function(){
      operation = {};
      controller = new DeploymentController($scope, location, resource, routeParams, dialog, deploymentDataParser, $http, urlBuilder, Deployment, workflow);
      $scope.load_workflow_stats(operation);
      expect(resource).not.toHaveBeenCalled();
    });

    it('should calculate statistics', function(){
      operation = { link: '5555/workflows/2saidjfio' };
      controller = new DeploymentController($scope, location, resource, routeParams, dialog, deploymentDataParser, $http, urlBuilder, Deployment, workflow);
      $scope.load_workflow_stats(operation);
      expect(resource.getCall(0).args[0]).toEqual('5555/workflows/2saidjfio.json');
    });
  });

  describe('#available_services', function() {
    it('should forward calls to Deployment service', function() {
      var deployment = 'fake deployment';
      Deployment.available_services = sinon.spy();
      $scope.available_services(deployment);
      expect(Deployment.available_services).toHaveBeenCalledWith('fake deployment');
    });
  });

  describe('#is_scalable_service', function() {
    var deployment, resource;
    beforeEach(function() {
      spyOn($scope, 'available_services').andReturn(['web']);
      deployment = { plan: { services: { web: { component: { instances: ['1'] } } } } };
      resource = { service: 'web', index: '1' };
    });

    it('should return true if service is scalable and resource index is in deployment plan', function() {
      expect($scope.is_scalable_service(resource, deployment)).toBe(true);
    });

    describe('should return false when', function() {
      it('resource has no service', function() {
        resource = {};
        expect($scope.is_scalable_service(resource, 'deployment')).toBe(false);
      });

      it('service is not in available_services', function() {
        $scope.available_services.andReturn([]);
        expect($scope.is_scalable_service(resource, deployment)).toBe(false);
      });

      it('resource index not in deployment plan', function() {
        deployment.plan.services.web.component.instances = [];
        expect($scope.is_scalable_service(resource, deployment)).toBe(false);
      });
    });
  });

  describe('#add_nodes', function() {
    var promise;
    beforeEach(function() {
      promise = { then: sinon.spy() };
      Deployment.add_nodes = sinon.stub().returns(promise);
      $scope.load = 'fake load';
      $scope.show_error = 'fake show error';
      $scope.add_nodes('deployment', 'service', 'num_nodes');
    });

    it('should forward calls to Deployment service', function() {
      expect(Deployment.add_nodes).toHaveBeenCalledWith('deployment', 'service', 'num_nodes');
    });

    it('should load() when call is successful', function() {
      expect(promise.then.getCall(0).args[0]).toEqual('fake load');
    });

    it('should show_error() when call is not successful', function() {
      expect(promise.then.getCall(0).args[1]).toEqual('fake show error');
    });
  });

  describe('#delete_nodes', function() {
    var promise, deployment;
    beforeEach(function() {
      promise = { then: sinon.spy() };
      Deployment.delete_nodes = sinon.stub().returns(promise);
      $scope.load = 'fake load';
      $scope.show_error = 'fake show error';
      var resource_map = { '1': true };
      var resource = { service: 'web' };
      deployment = { resources: { '1': resource } }
      $scope.delete_nodes(deployment, resource_map);
    });

    it('should forward calls to Deployment service', function() {
      expect(Deployment.delete_nodes).toHaveBeenCalledWith(deployment, 'web', 1, [{service: 'web'}]);
    });

    it('should load() when call is successful', function() {
      expect(promise.then.getCall(0).args[0]).toEqual('fake load');
    });

    it('should show_error() when call is not successful', function() {
      expect(promise.then.getCall(0).args[1]).toEqual('fake show error');
    });
  });

  describe('take_offline', function() {
    var deferred, $rootScope;
    beforeEach(inject(function($injector) {
      $rootScope = $injector.get('$rootScope');
      var $q = $injector.get('$q');
      deferred = $q.defer();
      Deployment.take_offline = sinon.stub().returns(deferred.promise);

      $scope.load = sinon.spy();
      $scope.notify = sinon.spy();
      $scope.show_error = sinon.spy();

      var deployment = 'fake deployment';
      var resource = { 'dns-name': 'fakename' };
      Deployment.get_application = sinon.stub().returns(resource);
      $scope.take_offline(deployment, resource);
    }));

    it('should forward calls to Deployment service', function() {
      expect(Deployment.take_offline).toHaveBeenCalledWith('fake deployment', {'dns-name': 'fakename'});
    });

    describe('- on success:', function() {
      beforeEach(function() {
        deferred.resolve('Success!');
        $rootScope.$apply();
      });

      it('should reload the page', function() {
        expect($scope.load).toHaveBeenCalled();
      });

      it('should notify the user', function() {
        expect($scope.notify).toHaveBeenCalledWith('fakename will be taken offline');
      });
    });

    describe('- on failure:', function() {
      beforeEach(function() {
        deferred.reject('Failure! =(');
        $rootScope.$apply();
      });

      it('should display the error', function() {
        expect($scope.show_error).toHaveBeenCalled();
      });
    });
  });

  describe('bring_online', function() {
    var deferred, $rootScope;
    beforeEach(inject(function($injector) {
      $rootScope = $injector.get('$rootScope');
      var $q = $injector.get('$q');
      deferred = $q.defer();
      Deployment.bring_online = sinon.stub().returns(deferred.promise);

      $scope.load = sinon.spy();
      $scope.notify = sinon.spy();
      $scope.show_error = sinon.spy();

      var deployment = 'fake deployment';
      var resource = { 'dns-name': 'fakename' };
      Deployment.get_application = sinon.stub().returns(resource);
      $scope.bring_online(deployment, resource);
    }));

    it('should forward calls to Deployment service', function() {
      expect(Deployment.bring_online).toHaveBeenCalledWith('fake deployment', {'dns-name': 'fakename'});
    });

    describe('- on success:', function() {
      beforeEach(function() {
        deferred.resolve('Success!');
        $rootScope.$apply();
      });

      it('should reload the page', function() {
        expect($scope.load).toHaveBeenCalled();
      });

      it('should notify the user', function() {
        expect($scope.notify).toHaveBeenCalledWith('fakename will be online shortly');
      });
    });

    describe('- on failure:', function() {
      beforeEach(function() {
        deferred.reject('Failure! =(');
        $rootScope.$apply();
      });

      it('should display the error', function() {
        expect($scope.show_error).toHaveBeenCalled();
      });
    });
  });
});
