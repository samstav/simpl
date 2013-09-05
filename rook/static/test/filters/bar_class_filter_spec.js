describe('barClass filter', function(){
  var barClassFilter;
  beforeEach(module('checkmate.filters'));
  beforeEach(inject(['barClassFilter', function(filter){
    barClassFilter = filter;
  }]));

  it('should classify UP as a success', function(){
    expect(barClassFilter('UP')).toEqual('bar-success');
  });

  it('should classify FAILED as a danger', function(){
    expect(barClassFilter('FAILED')).toEqual('bar-danger');
  });

  it('should classify DELETED as inverse', function(){
    expect(barClassFilter('DELETED')).toEqual('bar-inverse');
  });

  it('should classify COMPLETE as a success', function(){
    expect(barClassFilter('COMPLETE')).toEqual('bar-success')
  });

  it('should classify ERROR as a danger', function(){
    expect(barClassFilter('ERROR')).toEqual('bar-danger')
  });

  it('should not classify anything else', function(){
    expect(barClassFilter('BATMAN')).toEqual('');
  });
});
