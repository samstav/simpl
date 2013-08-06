describe('urlBuilder', function(){
  var resource_id,
      resource_type,
      region,
      tenantId,
      resource,
      username;

  beforeEach(module('checkmate.services'));
  beforeEach(inject(function(urlBuilder){
    this.urlBuilder = urlBuilder;
    resource_id = 'resource_id';
    resource_type = 'server';
    region = 'ORD';
    tenantId = '123';
    username = 'username';
    resource = {
      instance: {
        id: 'resource_id',
        public_ip: '0.0.0.0',
      },
      provider: 'nova', // 'nova', 'legacy', 'load-balancer', 'databases', other
      region: 'ORD',
    };
  }));

  describe('novaStatsURL', function(){
    it('should build a nova stats url', function(){
      var expected = 'https://reports.ohthree.com/ord/instance/resource_id';
      expect(this.urlBuilder.get_url('nova_stats', resource, tenantId, username)).toEqual(expected);
    });
  });

  describe('sshTo', function(){
    it('should build the ssh path to the given ip', function(){
      var expected = 'ssh://root@0.0.0.0';
      expect(this.urlBuilder.get_url('ssh', resource, tenantId, username)).toEqual('ssh://root@0.0.0.0');
    });
  });

  describe('myCloudURL', function(){
    beforeEach(function(){
      resource.region = 'REGION_HERE';
    });

    it('should build an open stack server url', function(){
      resource.provider = 'nova';
      var expected = 'https://mycloud.rackspace.com/a/username/#compute%2CcloudServersOpenStack%2CREGION_HERE/resource_id';
      expect(this.urlBuilder.get_url('my_cloud', resource, tenantId, username)).toEqual(expected);
    });

    it('should build a legacy server url', function(){
      resource.provider = 'legacy';
      var expected = 'https://mycloud.rackspace.com/a/username/#compute%2CcloudServers%2CREGION_HERE/resource_id';
      expect(this.urlBuilder.get_url('my_cloud', resource, tenantId, username)).toEqual(expected);
    });

    it('should build a database url', function(){
      resource.provider = 'databases';
      var expected = 'https://mycloud.rackspace.com/a/username/database#rax%3Adatabase%2CcloudDatabases%2CREGION_HERE/resource_id';
      expect(this.urlBuilder.get_url('my_cloud', resource, tenantId, username)).toEqual(expected);
    });

    it('should build a load balancer url', function(){
      resource.provider = 'load-balancer';
      var expected = 'https://mycloud.rackspace.com/a/username/load_balancers#rax%3Aload-balancer%2CcloudLoadBalancers%2CREGION_HERE/resource_id';
      expect(this.urlBuilder.get_url('my_cloud', resource, tenantId, username)).toEqual(expected);
    });
  });

  describe('cloudControlURL', function(){
    it('should use the london url if region is london', function(){
      var expected = 'https://lon.cloudcontrol.rackspacecloud.com/customer/123/next_gen_servers/LON/resource_id';
      resource.region = 'LON';
      expect(this.urlBuilder.get_url('cloud_control', resource, tenantId, username)).toEqual(expected);
    });

    it('should default any given region other than london to US endpoint', function(){
      var expected = 'https://us.cloudcontrol.rackspacecloud.com/customer/123/next_gen_servers/ORD/resource_id';
      expect(this.urlBuilder.get_url('cloud_control', resource, tenantId, username)).toEqual(expected);
    });

    it('should build the url for a load balancer', function(){
      var expected = 'https://us.cloudcontrol.rackspacecloud.com/customer/123/load_balancers/ORD/resource_id';
      resource.provider = 'load-balancer';
      expect(this.urlBuilder.get_url('cloud_control', resource, tenantId, username)).toEqual(expected);
    });

    it('should build the url for a database', function(){
      var expected = 'https://us.cloudcontrol.rackspacecloud.com/customer/123/dbaas/instances/ORD/resource_id';
      resource.provider = 'databases';
      expect(this.urlBuilder.get_url('cloud_control', resource, tenantId, username)).toEqual(expected);
    });

    it('should build the url for a legacy server', function(){
      var expected = 'https://us.cloudcontrol.rackspacecloud.com/customer/123/first_gen_servers/ORD/resource_id';
      resource.provider = 'legacy';
      expect(this.urlBuilder.get_url('cloud_control', resource, tenantId, username)).toEqual(expected);
    });
  });

  describe('#is_valid', function() {
    it('should be valid if resource provider is nova', function() {
      resource.provider = 'nova';
      expect(this.urlBuilder.is_valid(resource)).toBe(true);
    });

    it('should be valid if resource provider is legacy', function() {
      resource.provider = 'legacy';
      expect(this.urlBuilder.is_valid(resource)).toBe(true);
    });

    it('should be valid if resource provider is load-balancer', function() {
      resource.provider = 'load-balancer';
      expect(this.urlBuilder.is_valid(resource)).toBe(true);
    });

    it('should be valid if resource provider is databases', function() {
      resource.provider = 'databases';
      expect(this.urlBuilder.is_valid(resource)).toBe(true);
    });

    it('should not be valid otherwise', function() {
      resource.provider = 'custom';
      expect(this.urlBuilder.is_valid(resource)).toBe(false);
    });
  });
});
