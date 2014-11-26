describe('capitalize filter', function(){
  var capitalize;
  beforeEach(function(){
    module('checkmate.filters');
  });
  beforeEach(inject(['capitalizeFilter', function(filter){
    capitalizeFilter = filter;
  }]));

  it('should capitalize the first letter and lowercase the rest', function(){
    expect(capitalizeFilter('this is a test')).toEqual('This is a test');
  });

  it('should lowercase everything that is not the first letter', function(){
    expect(capitalizeFilter('ThiS iS a TEST')).toEqual('This is a test');
  });
});
