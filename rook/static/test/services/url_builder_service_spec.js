describe('urlBuilder', function(){
  var tenantId,
      username,
      resource,
      urlBuilder;

  beforeEach(module('checkmate.services'));
  beforeEach(inject(['urlBuilder', function(_urlBuilder){
    urlBuilder = _urlBuilder;
    tenantId = '123';
    username = 'username';
    resource = {
      instance: {
        id: 'resource_id',
        public_ip: '0.0.0.0',
      },
      provider: 'nova', // 'legacy', 'load-balancer', 'databases', other
      region: 'ORD',
    };
  }]));

  describe('#get_url', function() {
    it('should get URLs for Cloud Control', function() {
      var url = urlBuilder.get_url('cloud_control', resource, tenantId, username);
      expect(url).toContain('cloudcontrol.rackspacecloud.com');
    });

    it('should get URLs for My Cloud', function() {
      var url = urlBuilder.get_url('my_cloud', resource, tenantId, username);
      expect(url).toContain('mycloud.rackspace.com');
    });

    it('should get URLs for Nova Stats', function() {
      var url = urlBuilder.get_url('nova_stats', resource, tenantId, username);
      expect(url).toContain('reports.ohthree.com');
    });

    it('should get URLs for SSH', function() {
      var url = urlBuilder.get_url('ssh', resource, tenantId, username);
      expect(url).toContain('ssh://');
    });

    it('should not build a URL is resource is not valid', function() {
      resource.provider = 'custom';
      var url = urlBuilder.get_url('whatever', resource, tenantId, username);
      expect(url).toBe(undefined);
    });
  });

  describe('novaStatsURL', function(){
    it('should build a nova stats url', function(){
      var expected = 'https://reports.ohthree.com/ord/instance/resource_id';
      expect(urlBuilder.get_url('nova_stats', resource, tenantId, username)).toEqual(expected);
    });
  });

  describe('sshTo', function(){
    it('should build the ssh path to the given ip', function(){
      var expected = 'ssh://root@0.0.0.0';
      expect(urlBuilder.get_url('ssh', resource, tenantId, username)).toEqual('ssh://root@0.0.0.0');
    });
  });

  describe('myCloudURL', function(){
    beforeEach(function(){
      resource.region = 'REGION_HERE';
    });

    it('should build an open stack server url', function(){
      resource.provider = 'nova';
      var expected = 'https://mycloud.rackspace.com/a/username/#compute%2CcloudServersOpenStack%2CREGION_HERE/resource_id';
      expect(urlBuilder.get_url('my_cloud', resource, tenantId, username)).toEqual(expected);
    });

    it('should build a legacy server url', function(){
      resource.provider = 'legacy';
      var expected = 'https://mycloud.rackspace.com/a/username/#compute%2CcloudServers%2CREGION_HERE/resource_id';
      expect(urlBuilder.get_url('my_cloud', resource, tenantId, username)).toEqual(expected);
    });

    it('should build a database url', function(){
      resource.provider = 'databases';
      var expected = 'https://mycloud.rackspace.com/a/username/database#rax%3Adatabase%2CcloudDatabases%2CREGION_HERE/resource_id';
      expect(urlBuilder.get_url('my_cloud', resource, tenantId, username)).toEqual(expected);
    });

    it('should build a load balancer url', function(){
      resource.provider = 'load-balancer';
      var expected = 'https://mycloud.rackspace.com/a/username/load_balancers#rax%3Aload-balancer%2CcloudLoadBalancers%2CREGION_HERE/resource_id';
      expect(urlBuilder.get_url('my_cloud', resource, tenantId, username)).toEqual(expected);
    });
  });

  describe('cloudControlURL', function(){
    it('should use the london url if region is london', function(){
      var expected = 'https://lon.cloudcontrol.rackspacecloud.com/customer/123/next_gen_servers/LON/resource_id';
      resource.region = 'LON';
      expect(urlBuilder.get_url('cloud_control', resource, tenantId, username)).toEqual(expected);
    });

    it('should default any given region other than london to US endpoint', function(){
      var expected = 'https://us.cloudcontrol.rackspacecloud.com/customer/123/next_gen_servers/ORD/resource_id';
      expect(urlBuilder.get_url('cloud_control', resource, tenantId, username)).toEqual(expected);
    });

    it('should build the url for a load balancer', function(){
      var expected = 'https://us.cloudcontrol.rackspacecloud.com/customer/123/load_balancers/ORD/resource_id';
      resource.provider = 'load-balancer';
      expect(urlBuilder.get_url('cloud_control', resource, tenantId, username)).toEqual(expected);
    });

    it('should build the url for a database', function(){
      var expected = 'https://us.cloudcontrol.rackspacecloud.com/customer/123/dbaas/instances/ORD/resource_id';
      resource.provider = 'databases';
      expect(urlBuilder.get_url('cloud_control', resource, tenantId, username)).toEqual(expected);
    });

    it('should build the url for a legacy server', function(){
      var expected = 'https://us.cloudcontrol.rackspacecloud.com/customer/123/first_gen_servers/ORD/resource_id';
      resource.provider = 'legacy';
      expect(urlBuilder.get_url('cloud_control', resource, tenantId, username)).toEqual(expected);
    });
  });

  describe('#is_valid', function() {
    it('should be valid if resource provider is nova', function() {
      resource.provider = 'nova';
      expect(urlBuilder.is_valid(resource)).toBe(true);
    });

    it('should be valid if resource provider is legacy', function() {
      resource.provider = 'legacy';
      expect(urlBuilder.is_valid(resource)).toBe(true);
    });

    it('should be valid if resource provider is load-balancer', function() {
      resource.provider = 'load-balancer';
      expect(urlBuilder.is_valid(resource)).toBe(true);
    });

    it('should be valid if resource provider is databases', function() {
      resource.provider = 'databases';
      expect(urlBuilder.is_valid(resource)).toBe(true);
    });

    it('should not be valid otherwise', function() {
      resource.provider = 'custom';
      expect(urlBuilder.is_valid(resource)).toBe(false);
    });
  });
});
