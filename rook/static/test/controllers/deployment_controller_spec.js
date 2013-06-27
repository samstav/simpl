describe('DeploymentController', function(){
  var $scope,
      location,
      resource,
      routeParams,
      dialog,
      deploymentDataParser,
      $http,
      controller;

  beforeEach(function(){
    $scope = { $watch: sinon.spy() };
    location = { path: emptyFunction, absUrl: emptyFunction };
    resource = sinon.stub().returns({ get: emptyFunction });
    routeParams = undefined;
    dialog = undefined;
    deploymentDataParser = { formatData: emptyFunction };
    $http = { post: sinon.spy() };
    controller = new DeploymentController($scope, location, resource, routeParams, dialog, deploymentDataParser, $http);
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

  describe('#operation_status', function() {
    it('should return undefined if no operation exists', function() {
      expect($scope.operation_status()).toBe(undefined);
    });

    it('should return operation status if an operation exists', function() {
      $scope.data.operation = { status: 'fakestatus' };
      expect($scope.operation_status()).toBe('fakestatus');
    });
  });

  describe('#deployment_status', function() {
    it('should return deployment status', function() {
      $scope.data.status = 'deployment_fakestatus';
      expect($scope.deployment_status()).toBe('deployment_fakestatus');
    });

    describe('when operation exists', function() {
      beforeEach(function() {
        $scope.data.status = 'deployment_fakestatus';
        $scope.data.operation = { type: 'operation_faketype', status: 'operation_fakestatus' };
        $scope.operation_status = sinon.stub();
      });

      it('should return deployment status if operation is COMPLETE', function() {
        $scope.operation_status.returns('COMPLETE');
        expect($scope.deployment_status()).toBe('deployment_fakestatus');
      });

      it('should return deployment status if operation is ERROR', function() {
        $scope.operation_status.returns('ERROR');
        expect($scope.deployment_status()).toBe('deployment_fakestatus');
      });

      it('should return the operation type if operation is running', function() {
        $scope.operation_status.returns('fakestatus_running');
        expect($scope.deployment_status()).toBe('operation_faketype');
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
      spyOn(mixpanel, 'track');
      $scope.data = { id: 'fakeid', operation: { 'retry-link': 'fakelink', 'retriable': true } };
      $scope.retry();
    });

    it('should post to retry-lik', function() {
      expect($http.post).toHaveBeenCalledWith('fakelink');
    });

    it('should log information to mixpanel', function() {
      expect(mixpanel.track).toHaveBeenCalledWith('Deployment::Retry', { deployment_id: 'fakeid' });
    });
  });

  describe('#resume', function() {
    beforeEach(function() {
      spyOn($http, 'post');
      spyOn(mixpanel, 'track');
      $scope.data = { id: 'fakeid', operation: { 'resume-link': 'fakelink', 'resumable': true } };
      $scope.resume();
    });

    it('should post to resume-link', function() {
      expect($http.post).toHaveBeenCalledWith('fakelink');
    });

    it('should log information to mixpanel', function() {
      expect(mixpanel.track).toHaveBeenCalledWith('Deployment::Resume', { deployment_id: 'fakeid' });
    });
  });

  describe('#build_tree', function() {
    it('should set tree_data information', function() {
      $scope.build_tree();
      expect($scope.tree_data).toEqual({vertex_groups: [], edges: []});
    });

    it('should handle empty data', function() {
      expect($scope.build_tree()).toEqual({vertex_groups: [], edges: []});
    });

    describe('when resource is present', function() {
      var tree;
      beforeEach(function() {
        $scope.data.resources = {
          v1: {
            'index': 'v1',
            'service': 'fakegroup',
            'component': 'fakecomponent',
            'dns-name': 'fakename.example.com',
            'status': 'fakestatus',
            'relations': {},
            'hosted_on': '1'
          },
          v2: {
            'index': 'v2',
            'service': 'fakegroup2',
            'component': 'fakecomponent2',
            'dns-name': undefined,
            'status': 'fakestatus2',
            'relations': {},
            'hosted_on': '2'
          },
          v3: {}
        };
        tree = $scope.build_tree();
      });

      it('should skip resource with no relations', function() {
        expect(tree.vertex_groups[0].length).toBe(2);
      });

      it('should default group number to 0', function() {
        expect(tree.vertex_groups[0]).not.toBe(undefined);
      });

      it('should set vertex ID', function() {
        expect(tree.vertex_groups[0][0].id).toEqual('v1');
      });

      it('should set vertex group', function() {
        expect(tree.vertex_groups[0][0].group).toEqual('fakegroup');
      });

      it('should set vertex component', function() {
        expect(tree.vertex_groups[0][0].component).toEqual('fakecomponent');
      });

      it('should set vertex name', function() {
        expect(tree.vertex_groups[0][0].name).toEqual('fakename');
      });

      it('should set vertex status', function() {
        expect(tree.vertex_groups[0][0].status).toEqual('fakestatus');
      });

      it('should build tree with no edges if no relation is present', function() {
        expect(tree.edges).toEqual([]);
      });

      describe('and resource contains relations', function() {
        beforeEach(function() {
          $scope.data.resources.v1.relations = {
            r1: { relation: 'reference', target: 'v2' }
          };
          $scope.data.resources.v2.relations = {
            r1: { relation: 'reference', target: 'v1' }
          };
        });

        it('should skip relations that are not reference', function() {
          $scope.data.resources.v1.relations.r1.relation = 'fakerelation';
          $scope.data.resources.v2.relations.r1.relation = 'fakerelation';
          var tree = $scope.build_tree();
          expect(tree.edges).toEqual([]);
        });
      });
    });
  });
});
