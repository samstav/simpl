describe('ExternalController', function(){
  it('should assign the window location href to the locations absUrl', function(){
    var window = { location: {} },
        location = { absUrl: function(){ return 'lol.com'; } },
        controller = new ExternalController(window, location);
    expect(window.location.href).toEqual('lol.com');
  });
});

