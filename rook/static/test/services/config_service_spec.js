describe('config', function(){
  beforeEach(module('checkmate.services'));
  beforeEach(inject(function(config, _$location_){
    this.config = config;
    $location = _$location_;
  }));

  describe('environment', function(){
    it('should know the production environment', function(){
      sinon.stub($location, 'host').returns('checkmate.rackspace.com');
      expect(this.config.environment()).toBe('production');
    });

    it('should know the development environment', function(){
      sinon.stub($location, 'host').returns('localhost');
      expect(this.config.environment()).toBe('development');
    });
  });
});
