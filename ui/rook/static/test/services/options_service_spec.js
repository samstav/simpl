describe('options', function(){
  beforeEach(module('checkmate.services'));
  beforeEach(inject(function(options){
    this.options = options;
  }));

  describe('getOptionsFromBlueprint', function(){
    var blueprint;
    beforeEach(function(){
      blueprint = {};
    });

    it('should copy blueprint options and add the key as id', function(){
      blueprint = { options: { deployment: { required: true } } };
      expect(this.options.getOptionsFromBlueprint(blueprint).options).toEqual([{ required: true , id: 'deployment' }]);
    });

    it('should use default options_to_display if there is no reach info option groups', function(){
      blueprint = {};
      expect(this.options.getOptionsFromBlueprint(blueprint).options_to_display).toEqual(['application', 'server', 'load-balancer', 'database', 'dns']);
    });

    it('should use reach info option groups if present', function(){
      blueprint = {
        'meta-data': {
          'reach-info': {
            'option-groups': [ 'thou', 'shall', 'not', 'pass' ]
          }
        }
      };
      expect(this.options.getOptionsFromBlueprint(blueprint).options_to_display).toEqual(['thou', 'shall', 'not', 'pass']);
    });

    describe('option does not have display hints', function(){
      it('should add "application" to groups if key is site_address', function(){
        blueprint = { options:
          { site_address:
            { something: 'www.rackspace.com' }
          }
        };

        expect(this.options.getOptionsFromBlueprint(blueprint).groups['application']).toEqual([{ id: 'site_address', something: 'www.rackspace.com', type: 'url' }]);
      });

      it('should add "application" to groups if key is url', function(){
        blueprint = { options:
          { url:
            { something: 'www.rackspace.com' }
          }
        };

        expect(this.options.getOptionsFromBlueprint(blueprint).groups['application']).toEqual([{ id: 'url', something: 'www.rackspace.com', type: 'url' }]);
      });

      it('should add "application" to groups if key is url', function(){
        blueprint = { options:
          { url:
            { something: 'www.rackspace.com' }
          }
        };

        expect(this.options.getOptionsFromBlueprint(blueprint).groups['application']).toEqual([{ id: 'url', something: 'www.rackspace.com', type: 'url' }]);
      });

      it('should add option to the application option group if it doesnt fall into another category', function(){
        blueprint = { options:
          { unknownOption:
            { something: 'www.rackspace.com' }
          }
        };

        expect(this.options.getOptionsFromBlueprint(blueprint).groups['application']).toEqual([{ id: 'unknownOption', something: 'www.rackspace.com'}]);
      });
    });

    describe('option has display hints', function(){
      it('should set the option order to the hint order', function(){
        blueprint = { options:
          { deployment:
            { 'display-hints': { order: 'QQQ' } }
          }
        };
        expect(this.options.getOptionsFromBlueprint(blueprint).options[0].order).toEqual('QQQ');
      });

      it('should set the option order to XXX if there is no hint order', function(){
        blueprint = { options:
          { deployment:
            { 'display-hints': { order: null } }
          }
        };
        expect(this.options.getOptionsFromBlueprint(blueprint).options[0].order).toEqual('XXX');
      });

      it('should set region option if option is type region', function(){
        blueprint = { options:
          { blahblah:
            { type: 'region' }
          }
        };
        expect(this.options.getOptionsFromBlueprint(blueprint).region_option).toEqual({ id: 'blahblah', type: 'region' });
      });

      it('should set region option if option has key of region', function(){
        blueprint = { options:
          { region:
            { required: true }
          }
        };
        expect(this.options.getOptionsFromBlueprint(blueprint).region_option).toEqual({ id: 'region', required: true });
      });

      it('should set sample if display hint has sample', function(){
        blueprint = { options:
          { deployment:
            { 'display-hints': { sample: 'cats' } }
          }
        };
        expect(this.options.getOptionsFromBlueprint(blueprint).options[0].sample).toEqual('cats');
      });

      it('should set choice if display hint has choice', function(){
        blueprint = { options:
          { deployment:
            { 'display-hints': { choice: 'cats' } }
          }
        };
        expect(this.options.getOptionsFromBlueprint(blueprint).options[0].choice).toEqual('cats');
      });

      it('should set encrypted protocols if display hint has protocols', function(){
        blueprint = { options:
          { deployment:
            { 'display-hints': { 'encrypted-protocols': 'cats' } }
          }
        };
        expect(this.options.getOptionsFromBlueprint(blueprint).options[0]['encrypted-protocols']).toEqual('cats');
      });

      it('should set always-accept-certificates', function(){
        blueprint = { options:
          { deployment:
            { 'display-hints': { 'always-accept-certificates': 'cats' } }
          }
        };
        expect(this.options.getOptionsFromBlueprint(blueprint).options[0]['always-accept-certificates']).toEqual('cats');
      });

      it('should add option to application group if dh doesnt have a group', function(){
        blueprint = { options:
          { deployment:
            { 'display-hints': { 'cheese': 'cats' } }
          }
        };
        expect(this.options.getOptionsFromBlueprint(blueprint).groups['application']).toEqual([{ id: 'deployment', 'display-hints': { cheese: 'cats' }, order: 'XXX' }]);
      });
    });
  });
});

