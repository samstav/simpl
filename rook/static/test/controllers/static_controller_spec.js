describe('StaticController', function(){
  it('should not display the header', function(){
    var scope = {},
        location = { path: emptyFunction },
        controller = new StaticController(scope, location);

    expect(scope.showHeader).toBeFalsy();
  });

  it('should not display status', function(){
    var scope = {},
        location = { path: emptyFunction },
        controller = new StaticController(scope, location);

    expect(scope.showStatus).toBeFalsy();
  });
});

