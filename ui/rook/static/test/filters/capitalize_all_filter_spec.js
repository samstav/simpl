describe('capitalizeAll filter', function(){
  beforeEach(module('checkmate.filters'));
  beforeEach(inject(['capitalizeAllFilter', function(filter){
    capitalizeAllFilter = filter;
  }]));

  it('should capitalize each word in the line', function(){
    expect(capitalizeAllFilter('this is a test')).toEqual('This Is A Test');
  });
});
