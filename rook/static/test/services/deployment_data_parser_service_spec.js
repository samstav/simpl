describe('deploymentDataParser', function(){
  var data;

  beforeEach(module('checkmate.services'));
  beforeEach(inject(function(deploymentDataParser){
    this.deploymentDataParser = deploymentDataParser;
  }));

  describe('formatData', function(){
    it('should parse and format the url from returned data', function(){
      var data = { inputs:
                           { blueprint:
                                        { url: "http://www.ok.com"}
                           }
                 },
          result = this.deploymentDataParser.formatData(data);

      expect(result.path).toEqual('http://www.ok.com');
    });

    it('should parse and format the url if it is an object with a url property', function(){
      var data = { inputs:
                           { blueprint:
                                        { url:
                                               { url: "http://www.ok.com"}
                                        }
                           }
                 },
          result = this.deploymentDataParser.formatData(data);

      expect(result.path).toEqual('http://www.ok.com');
      expect(result.domain).toEqual('www.ok.com');
    });

    it('should derive domain and url from blueprint object if there is no url', function(){
      var data = { inputs:
                           { blueprint:
                                        { domain: "www.ok.com", path: ""}
                           }
                 },
          result = this.deploymentDataParser.formatData(data);

      expect(result.domain).toEqual('www.ok.com');
      expect(result.path).toEqual('http://www.ok.com');
    });

    it('should get the load balancer IP', function(){
      var data = { resources: { "0":
                                { type: 'load-balancer',
                                  instance: { public_ip: '1.1.1.1' } }
                              },
                   inputs: { blueprint: { url: 'http://www.disney.com' } }
                 },
          result = this.deploymentDataParser.formatData(data);

      expect(result.vip).toEqual('1.1.1.1');
    });

    it('should use the load balancer to build path if it couldnt find a domain', function(){
      var data = { resources: { "0":
                                { type: 'load-balancer',
                                  instance: { public_ip: '1.1.1.1' } }
                              }
                 },
          result = this.deploymentDataParser.formatData(data);

      expect(result.path).toEqual('http://1.1.1.1/');
    });

    it('should set the username and password', function(){
      var data = { resources: { "0":
                                { type: 'user',
                                  instance: { name: 'racker',
                                              password: 'omgwtfbbq' } }
                              }
                 },
          result = this.deploymentDataParser.formatData(data);

      expect(result.username).toEqual('racker');
      expect(result.password).toEqual('omgwtfbbq');
    });

    it('should set the private key', function(){
      var data = { resources: { "0":
                                { type: 'key-pair',
                                  instance: { private_key: 'PRIVATEKEY' }
                                }
                              }
                 },
          result = this.deploymentDataParser.formatData(data);

      expect(result.private_key).toEqual('PRIVATEKEY');
    });

    it('should transform resources into an array for angular filters to work better', function(){
      var data = { resources: { "0":
                                { type: 'key-pair' },
                                "1":
                                { type: 'user' }
                              }
                 },
          result = this.deploymentDataParser.formatData(data);

      expect(result.resources.length).toEqual(2);
      expect(result.resources[0]).toEqual({ type: 'key-pair' });
      expect(result.resources[1]).toEqual({ type: 'user' });
    });

    it('should set the master server', function(){
      var master_server = { component: 'linux_instance',
                            service: 'master',
                            instance: { password: 'cats' }  },
          data = { resources: { "0": master_server }
                 },
          result = this.deploymentDataParser.formatData(data);

      expect(result.master_server).toEqual(master_server);
    });

    it('should not set the master server if no master', function(){
      var data = { resources: { "0":
                                { component: 'linux_instance', service: 'slave',
                                  instance: { password: 'cats' }  }
                              }
                 },
          result = this.deploymentDataParser.formatData(data);

      expect(result.master_server).toBeUndefined();
    });
  });
});
