describe('capitalize_all filter', function(){
  beforeEach(function(){
    module('checkmate.filters');
  });

  it('should capitalize each word in the line', inject(function(capitalize_allFilter){
    expect(capitalize_allFilter('this is a test')).toEqual('This Is A Test');
  }));
});
