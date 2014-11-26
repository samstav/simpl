describe('items', function(){
  var items;
  beforeEach(module('checkmate.services'));
  beforeEach(inject(['items', function(items_service){
    items = items_service;
  }]));

  describe('#receive', function(){
    var data;
    beforeEach(function(){
      data = undefined;
    });
    it('should return the total item count', function(){
      data = [{ name: 'cat' },
              { name: 'dog' }];
      expect(items.receive(data).count).toEqual(2);
    });

    describe('all', function(){
      it('should return the unchanged items if no transform function', function(){
        data = [{ name: 'cat' },
                { name: 'dog' }];
        expect(items.receive(data).all).toEqual(data);
      });

      it('should return the transformed items if given transform function', function(){
        data = [{ name: 'cat' },
                { name: 'dog' }];
        expect(items.receive(data, function(value, key){
          return { bat: value.name };
        }).all).toEqual([{ bat: 'cat' }, { bat: 'dog' }]);
      });
    });

    describe('data', function(){
      it('should return data as an object instead of array', function(){
        data = [{ name: 'cat' },
                { 'batman': 'rich' }];
        expect(items.receive(data).data).toEqual({ 0: { name: 'cat' }, 1: { batman: 'rich' } });
      });
    });
  });
});
