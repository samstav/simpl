describe('Deployment service', function(){
  var WorkflowSpec;

  beforeEach(module('checkmate.services'));
  beforeEach(inject(function($injector) {
    WorkflowSpec = $injector.get('WorkflowSpec');
  }));

  describe('#to_streams', function(){

    describe('Empty Streams:', function() {
      var empty_streams;
      beforeEach(function() {
        empty_streams = WorkflowSpec.to_streams();
      });

      it('should contain an array with all streams', function() {
        expect(empty_streams.all).toEqual([]);
      });

      it('width should be zero', function() {
        expect(empty_streams.width).toBe(0);
      });
    });

    describe('With Invalid Specs:', function() {
      var invalid_specs, streams;
      beforeEach(function() {
        invalid_specs = {
          'undefined spec': undefined,
          'no properties': { pseudo_properties: {} },
          'inputs length is zero': { inputs: [], outputs: ['blah'] },
          'no inputs and no outputs(Root node)': { inputs: [], outputs: [] }
        };
        streams = WorkflowSpec.to_streams(invalid_specs);
      });

      it('should skip all invalid specs', function() {
        expect(streams.all.length).toBe(0);
      });
    });

    describe('With Valid Specs:', function() {
      var spec, specs, streams;
      beforeEach(function() {
        spec = {
          id: 1,
          properties: { resource: '0' },
          inputs: [ '1' ],
          outputs: [ '2' ]
        };
        specs = { 'First Spec': spec };
        streams = WorkflowSpec.to_streams(specs);
      });

      it('should return stream nodes sorted by key', function(){
        var spec_2 = {
          id: 2,
          properties: { resource: '0' },
          inputs: [ 'Alpha Spec' ],
          outputs: []
        };
        var spec_3 = {
          id: 3,
          properties: { resource: '0' },
          inputs: [ 'Alpha Spec' ],
          outputs: []
        };
        var deployment = { resources: {} };
        specs = { 'Zeta Spec': spec_3, 'Bravo Spec': spec_2, 'Alpha Spec': spec };
        streams = WorkflowSpec.to_streams(specs);
        expect(streams.nodes).toEqual([spec, spec_2, spec_3])
      });

      it('if no resource ID in properties, read it from the inputs', function() {
        spec = {
          id: 1,
          properties: { resource: '0' },
          inputs: [ '1' ]
        };
        var no_resource_in_properties_spec = {
          id: 1,
          properties: { no_resource: true },
          inputs: [ 'First Spec' ]
        };
        specs = { 'First Spec': spec, 'Lookup Spec': no_resource_in_properties_spec };
        var deployment = { resources: {} };
        streams = WorkflowSpec.to_streams(specs, deployment);
      });

      it('should include the Start node if it is a custom deployment (has an "end" node)', function(){
        var start_node = {
          id: 1,
          properties: { resource: '0' },
          inputs: [],
          outputs: [ 'end' ]
        };
        var end_node = {
          id: 2,
          properties: { resource: '0' },
          inputs: [ 'Start' ],
          outputs: []
        };
        var deployment = { resources: {} };
        specs = { 'end': end_node, 'Start': start_node };
        streams = WorkflowSpec.to_streams(specs);
        expect(streams.nodes).toEqual([start_node, end_node])
      });

      it('should contain one stream', function() {
        expect(streams.all.length).toBe(1);
      });

      it('should add spec to streams all_specs array', function() {
        expect(streams.all[0].data).toContain(spec);
      });

      it('should contain a streams indexed by the resource id', function() {
        expect(streams['0']).toEqual(streams.all[0]);
      });

      it('should contain a width property with the max spec distance from start', function() {
        expect(streams.width).toBe(0);
      });

      describe('Stream:', function() {
        var stream;
        beforeEach(function() {
          stream = streams['0'];
        });

        it('should contain an icon', function() {
          expect(stream.icon).toBe('');
        });

        it('should contain stream data', function() {
          expect(stream.data.length).toBe(1);
        });

        it('should contain a title', function() {
          expect(stream.title).toBe('');
        });

        it('should contain a position starting from zero', function() {
          expect(stream.position).toBe(0);
        });
      });
    });

  });
});
