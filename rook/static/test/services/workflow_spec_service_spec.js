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
          'no inputs': { pseudo_inputs: [] },
          'inputs length is zero': { inputs: [] }
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
          inputs: [ '1' ]
        };
        specs = { 'First Spec': spec };
        streams = WorkflowSpec.to_streams(specs);
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
        streams = WorkflowSpec.to_streams(specs);
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
          expect(stream.icon).toBe(null);
        });

        it('should contain stream data', function() {
          expect(stream.data.length).toBe(1);
        });

        it('should contain a title', function() {
          expect(stream.title).toBe(null);
        });

        it('should contain a position', function() {
          expect(stream.position).toBe(0);
        });
      });
    });

  });
});
