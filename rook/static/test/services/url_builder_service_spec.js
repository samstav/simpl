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

  describe('novaStatsURL', function(){
    it('should build a nova stats url', function(){
      var expected = 'https://reports.ohthree.com/ord/instance/resource_id';
      expect(this.urlBuilder.novaStatsURL(region, resource_id)).toEqual(expected);
    });
  });

  describe('myCloudURL', function(){
    var username;
    beforeEach(function(){
      username = 'username';
    });

    it('should build an open stack server url', function(){
      region = 'REGION_HERE';
      var expected = 'https://mycloud.rackspace.com/a/username/#compute%2CcloudServersOpenStack%2CREGION_HERE/resource_id';
      expect(this.urlBuilder.myCloudURL('server', username, region, resource_id)).toEqual(expected);
    });

    it('should build a legacy server url', function(){
      region = 'REGION_HERE';
      var expected = 'https://mycloud.rackspace.com/a/username/#compute%2CcloudServers%2CREGION_HERE/resource_id';
      expect(this.urlBuilder.myCloudURL('legacy_server', username, region, resource_id)).toEqual(expected);
    });

    it('should build a database url', function(){
      region = 'REGION_HERE';
      var expected = 'https://mycloud.rackspace.com/a/username/database#rax%3Adatabase%2CcloudDatabases%2CREGION_HERE/resource_id';
      expect(this.urlBuilder.myCloudURL('database', username, region, resource_id)).toEqual(expected);
    });

    it('should build a load balancer url', function(){
      region = 'REGION_HERE';
      var expected = 'https://mycloud.rackspace.com/a/username/load_balancers#rax%3Aload-balancer%2CcloudLoadBalancers%2CREGION_HERE/resource_id';
      expect(this.urlBuilder.myCloudURL('load_balancer', username, region, resource_id)).toEqual(expected);
    });
  });

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
      resource_type = 'legacy_server';
      expect(this.urlBuilder.cloudControlURL(resource_type, resource_id, region, tenantId)).toEqual(expected);
    });
  });
});
