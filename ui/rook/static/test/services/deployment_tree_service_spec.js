describe('DeploymentTree service', function() {

  var DeploymentTree,
      deployment;

  beforeEach(module('checkmate.services'));
  beforeEach(inject(function($injector) {
    DeploymentTree = $injector.get('DeploymentTree');
    deployment = {};
  }));

  describe('#build', function() {
    it('should return tree_data information', function() {
      var tree_data = DeploymentTree.build({});
      expect(tree_data).toEqual({vertex_groups: [], edges: []});
    });

    describe('when resource is present', function() {
      var tree;
      beforeEach(function() {
        deployment.resources = {
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
        tree = DeploymentTree.build(deployment);
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
          deployment.resources.v1.relations = {
            r1: { relation: 'reference', target: 'v2' }
          };
          deployment.resources.v2.relations = {
            r1: { relation: 'reference', target: 'v1' }
          };
        });

        it('should skip relations that are not reference', function() {
          deployment.resources.v1.relations.r1.relation = 'fakerelation';
          deployment.resources.v2.relations.r1.relation = 'fakerelation';
          var tree = DeploymentTree.build(deployment);
          expect(tree.edges).toEqual([]);
        });
      });
    });
  });
});
