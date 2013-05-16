describe('github', function(){
  var remote,
      url,
      content_item,
      callback;

  describe('get_contents', function(){
    beforeEach(module('checkmate.services'));

    beforeEach(inject(function(github, $http, $injector){
      $httpBackend = $injector.get('$httpBackend');
      this.github = github;
      remote = { api: { server: 'https://someserver.com' } };
      callback = emptyFunction;
    }));

    afterEach(function(){
      $httpBackend.verifyNoOutstandingExpectation();
      $httpBackend.verifyNoOutstandingRequest();
    });

    it('should call the github api through our proxy to get file contents', function(){
      $httpBackend.when('GET', '/githubproxy/this/is/a/path/contents/checkmate.yaml').respond({});
      $httpBackend.expectGET('/githubproxy/this/is/a/path/contents/checkmate.yaml');
      url = 'https://omgwtfbbq.com/this/is/a/path';
      content_item = "checkmate.yaml";

      this.github.get_contents(remote, url, content_item, callback);
      $httpBackend.flush();
    });
  });
});
