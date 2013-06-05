describe('webengage', function(){
  beforeEach(module('checkmate.services'));
  beforeEach(inject(function(webengage, config){
    this.webengage = webengage;
    this.config = config;
  }));

  describe('init', function(){
    var webengage_element;
    beforeEach(function(){
      webengage_element = { parentNode: { insertBefore: emptyFunction } };
      sinon.stub(document, 'getElementById').returns(webengage_element);
    });

    afterEach(function(){
      document.getElementById.restore();
      window.webengage = undefined;
      window.webengageWidgetInit = undefined;
    });

    it('should call some copy/pasted code from the webengage website', function(){
      sinon.stub(this.config, 'environment').returns('local');
      this.webengage.init();
      expect(window.webengageWidgetInit).toBeDefined();
    });

    it('should use the localhost license code when in local', function(){
      sinon.stub(this.config, 'environment').returns('local');
      window.webengage = { init: sinon.stub().returns({ onReady: sinon.stub() }) };
      this.webengage.init();
      window.webengageWidgetInit();

      expect(window.webengage.init.getCall(0).args[0]).toEqual({ licenseCode: '~99198c48' });
      this.config.environment.restore();
    });

    it('should use the .com production license code when in .com production', function(){
      sinon.stub(this.config, 'environment').returns('production.com');
      window.webengage = { init: sinon.stub().returns({ onReady: sinon.stub() }) };
      this.webengage.init();
      window.webengageWidgetInit();

      expect(window.webengage.init.getCall(0).args[0]).toEqual({ licenseCode: '~2024bc52' });
      this.config.environment.restore();
    });

    it('should use the .net production license code when in .net production', function(){
      sinon.stub(this.config, 'environment').returns('production.net');
      window.webengage = { init: sinon.stub().returns({ onReady: sinon.stub() }) };
      this.webengage.init();
      window.webengageWidgetInit();

      expect(window.webengage.init.getCall(0).args[0]).toEqual({ licenseCode: '~10a5cb78d' });
      this.config.environment.restore();
    });

    it('should use the dev license code when in dev', function(){
      sinon.stub(this.config, 'environment').returns('dev');
      window.webengage = { init: sinon.stub().returns({ onReady: sinon.stub() }) };
      this.webengage.init();
      window.webengageWidgetInit();

      expect(window.webengage.init.getCall(0).args[0]).toEqual({ licenseCode: '~c2ab32db' });
      this.config.environment.restore();
    });

    it('should not initialize webengage if there is no license code for the environment', function(){
      sinon.stub(this.config, 'environment').returns('prepreprodev');
      this.webengage.init();
      expect(window.webengageWidgetInit).toBeUndefined();
    });
  });
});
