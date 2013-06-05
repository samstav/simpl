describe('config', function(){
  beforeEach(module('checkmate.services'));
  beforeEach(inject(function(config, _$location_){
    this.config = config;
    $location = _$location_;
  }));

  describe('environment', function(){
    it('should know the .com production environment', function(){
      sinon.stub($location, 'host').returns('checkmate.rackspace.com');
      expect(this.config.environment()).toBe('production.com');
    });

    it('should know the .net production environment', function(){
      sinon.stub($location, 'host').returns('checkmate.rackspace.net');
      expect(this.config.environment()).toBe('production.net');
    });

    it('should know the local environment', function(){
      sinon.stub($location, 'host').returns('localhost');
      expect(this.config.environment()).toBe('local');
    });

    it('should know the development environment', function(){
      sinon.stub($location, 'host').returns('api.dev.chkmate.rackspace.net');
      expect(this.config.environment()).toBe('dev');
    });

    it('should know the staging environment', function(){
      sinon.stub($location, 'host').returns('staging.chkmate.rackspace.net');
      expect(this.config.environment()).toBe('staging');
    });

    it('should know the QA environment', function(){
      sinon.stub($location, 'host').returns('api.qa.chkmate.rackspace.net');
      expect(this.config.environment()).toBe('qa');
    });

    it('should know the preprod environment', function(){
      sinon.stub($location, 'host').returns('preprod.chkmate.rackspace.net');
      expect(this.config.environment()).toBe('preprod');
    });
  });
});
