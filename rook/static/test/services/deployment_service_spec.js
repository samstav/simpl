describe('Deployment service', function(){
  var Deployment,
      deployment,
      operation,
      $httpBackend;

  beforeEach(module('checkmate.services'));
  beforeEach(inject(function($injector) {
    Deployment = $injector.get('Deployment');
    $httpBackend = $injector.get('$httpBackend');
    deployment = {};
    operation = {};
  }));

  afterEach(function() {
    $httpBackend.verifyNoOutstandingExpectation();
    $httpBackend.verifyNoOutstandingRequest();
  });

  describe('status', function(){
    it('should return the deployment status', function(){
      deployment = { status: 'fakestatus' };
      expect(Deployment.status(deployment)).toEqual('fakestatus');
    });

    describe('when operation exists', function() {

      it('should return deployment status if operation is COMPLETE', function() {
        operation = { status: 'COMPLETE', type: 'sometype' };
        deployment = { status: 'fakestatus', operation: operation };
        expect(Deployment.status(deployment)).toBe('fakestatus');
      });

      it('should return deployment status if operation is ERROR', function() {
        operation = { status: 'ERROR', type: 'sometype' };
        deployment = { status: 'fakestatus', operation: operation };
        expect(Deployment.status(deployment)).toBe('fakestatus');
      });

      it('should return the operation type if operation is running', function() {
        operation = { status: 'IN PROGRESS', type: 'sometype' };
        deployment = { status: 'fakestatus', operation: operation };
        expect(Deployment.status(deployment)).toBe('sometype');
      });
    });
  });

  describe('progress', function(){
    it('should return 100 if all operation tasks are complete', function(){
      deployment = { operation: { complete: 50, tasks: 50 } };
      expect(Deployment.progress(deployment)).toBe(100);
    });

    it('should return 0 if no operation tasks are complete', function(){
      deployment = { operation: { complete: 0, tasks: 50 } };
      expect(Deployment.progress(deployment)).toBe(0);
    });

    it('should return the percent of tasks that are complete', function(){
      deployment = { operation: { complete: 10, tasks: 50 } };
      expect(Deployment.progress(deployment)).toBe(20);
    });

    it('should return 0 if no operation exists', function(){
      deployment = {};
      expect(Deployment.progress(deployment)).toBe(0);
    });

    it('should return 100 if the deployment failed', function(){
      deployment = { status: 'FAILED' };
      expect(Deployment.progress(deployment)).toBe(100);
    });
  });

  describe('#add_nodes', function() {
    it('should post deployment information to server', function() {
      var deployment = { id: 987, tenantId: 123 };
      var service_name = 'web';
      var num_nodes = 3;
      $httpBackend.expectPOST('/123/deployments/987/+add-nodes.json', { service_name: 'web', count: 3 }).respond(200, '');
      Deployment.add_nodes(deployment, service_name, num_nodes);
      $httpBackend.flush();
    });
  });

  describe('#delete_nodes', function() {
    var deployment, resources;
    beforeEach(function() {
      resources = {};
      resources = [
        { index: '0', service: 'web' },
        { index: '1', service: 'web' },
        { index: '2', service: 'web' },
      ];

      deployment = { id: 987, tenantId: 123, service: 'web' };
      deployment.plan = { services: { web: { component: { instances: ['0', '1', '2'] } } } };
      deployment.resources = {
        '0': resources[0],
        '1': resources[1],
        '2': resources[2],
      };
    });

    afterEach(function() {
      $httpBackend.flush();
    })

    it('should post a list of comma separated resource ids', function() {
      $httpBackend.expectPOST('/123/deployments/987/+delete-nodes.json', { resource_ids: "0,1,2" }).respond(200, '');
      Deployment.delete_nodes(deployment, resources);
    });

    it('should include only resources in service plan', function() {
      deployment.plan.services.web.component.instances = ['0', '2'];
      $httpBackend.expectPOST('/123/deployments/987/+delete-nodes.json', { resource_ids: "0,2" }).respond(200, '');
      Deployment.delete_nodes(deployment, resources);
    });

    describe('if resource not in deployment plan', function() {
      it('should find parent to delete', function() {
        resources = [
          { index: '1', service: 'web', hosted_on: '0' },
        ];
        deployment.plan.services.web.component.instances = ['0'];
        $httpBackend.expectPOST('/123/deployments/987/+delete-nodes.json', { resource_ids: "0" }).respond(200, '');
        Deployment.delete_nodes(deployment, resources);
      });

      it('should find child to delete', function() {
        resources = [
          { index: '1', service: 'web', hosts: ['0'] },
        ];
        deployment.plan.services.web.component.instances = ['0'];
        $httpBackend.expectPOST('/123/deployments/987/+delete-nodes.json', { resource_ids: "0" }).respond(200, '');
        Deployment.delete_nodes(deployment, resources);
      });
    });
  });

  describe('#available_services', function() {
    var deployment, count_setting;
    beforeEach(function() {
      deployment = {};
      count_setting = { setting: 'count' }
    });

    it('should return list of services with count contraint', function() {
      deployment.blueprint = { services: {
        web: { constraints: [ count_setting ] },
        app: { constraints: [ { other: 'custom' }, count_setting ] },
      } };
      expect(Deployment.available_services(deployment)).toContain('web');
      expect(Deployment.available_services(deployment)).toContain('app');
    });

    it('should return an empty list otherwise', function() {
      expect(Deployment.available_services(deployment)).toEqual([]);
    });
  });
});
