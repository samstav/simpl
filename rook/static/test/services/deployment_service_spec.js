describe('deployment', function(){
  var Deployment,
      deployment,
      operation;

  beforeEach(module('checkmate.services'));
  beforeEach(inject(['Deployment', function(deployment_service){
    Deployment = deployment_service;
    deployment = {};
    operation = {};
  }]));

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
});
