describe('urlBuilder', function(){
  var resource_id,
      resource_type,
      region,
      tenantId;

  beforeEach(module('checkmate.services'));
  beforeEach(inject(function(urlBuilder){
    this.urlBuilder = urlBuilder;
    resource_id = 'resource_id';
    resource_type = 'server';
    region = 'ORD';
    tenantId = '123';
  }));

  describe('cloudControlURL', function(){
    it('should use the london url if region is london', function(){
      var expected = 'https://lon.cloudcontrol.rackspacecloud.com/customer/123/next_gen_servers/LON/resource_id';
      region = 'LON';
      expect(this.urlBuilder.cloudControlURL(resource_type, resource_id, region, tenantId)).toEqual(expected);
    });

    it('should default any given region other than london to US endpoint', function(){
      var expected = 'https://us.cloudcontrol.rackspacecloud.com/customer/123/next_gen_servers/ORD/resource_id';
      expect(this.urlBuilder.cloudControlURL(resource_type, resource_id, region, tenantId)).toEqual(expected);
    });

    it('should build the url for a load balancer', function(){
      var expected = 'https://us.cloudcontrol.rackspacecloud.com/customer/123/load_balancers/ORD/resource_id';
      resource_type = 'load_balancer';
      expect(this.urlBuilder.cloudControlURL(resource_type, resource_id, region, tenantId)).toEqual(expected);
    });

    it('should build the url for a database', function(){
      var expected = 'https://us.cloudcontrol.rackspacecloud.com/customer/123/dbaas/instances/ORD/resource_id';
      resource_type = 'database';
      expect(this.urlBuilder.cloudControlURL(resource_type, resource_id, region, tenantId)).toEqual(expected);
    });

    it('should build the url for a legacy server', function(){
      var expected = 'https://us.cloudcontrol.rackspacecloud.com/customer/123/first_gen_servers/ORD/resource_id';
      resource_type = 'legacy';
      expect(this.urlBuilder.cloudControlURL(resource_type, resource_id, region, tenantId)).toEqual(expected);
    });
  });
});
