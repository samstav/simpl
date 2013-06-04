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
      this.webengage.init();
      expect(window.webengageWidgetInit).toBeDefined();
    });

    it('should use the localhost license code when in development', function(){
      sinon.stub(this.config, 'environment').returns('development');
      window.webengage = { init: sinon.stub().returns({ onReady: sinon.stub() }) };
      this.webengage.init();
      window.webengageWidgetInit();

      expect(window.webengage.init.getCall(0).args[0]).toEqual({ licenseCode: '~99198c48' });
      this.config.environment.restore();
    });

    it('should use the production license code when in production', function(){
      sinon.stub(this.config, 'environment').returns('production');
      window.webengage = { init: sinon.stub().returns({ onReady: sinon.stub() }) };
      this.webengage.init();
      window.webengageWidgetInit();

      expect(window.webengage.init.getCall(0).args[0]).toEqual({ licenseCode: '~2024bc52' });
      this.config.environment.restore();
    });
  });
});
