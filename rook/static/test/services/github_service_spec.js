describe('github service', function(){
  var remote,
      url,
      content_item,
      callback;

  var $httpBackend,
      github;

  beforeEach(module('checkmate.services'));
  beforeEach(inject(function($injector) {
    $rootScope = $injector.get('$rootScope');
    $httpBackend = $injector.get('$httpBackend');
    github = $injector.get('github');
  }));

  afterEach(function() {
    $httpBackend.verifyNoOutstandingExpectation();
    $httpBackend.verifyNoOutstandingRequest();
  });

  describe('#get_refs', function() {
    var repo1, repo2, repos;

    beforeEach(function() {
      repo1 = { git_refs_url: "http://github.com/org/repo1/refs{/sha}" };
      repo2 = { git_refs_url: "http://github.com/org/repo2/refs{/sha}" };
      repos = [repo1, repo2];
    });

    function resolve_promise(promise) {
      var result;
      promise.then(function(response) {
        result = response;
      });
      $rootScope.$apply();
      return result;
    }

    it('should return a promise with the requested refs', function() {
      $httpBackend.when('GET', '/githubproxy/org/repo1/refs').respond(404);
      var promise = github.get_refs(repo1);
      $httpBackend.flush();
      expect(promise.then).not.toBe(undefined);
    });

    it('should return an empty array when request fails', function() {
      $httpBackend.when('GET', '/githubproxy/org/repo1/refs').respond(404);
      var promise = github.get_refs(repo1);
      $httpBackend.flush();
      var result = resolve_promise(promise);
      expect(result).toEqual([]);
    });

    it('should get refs for a single repo', function() {
      $httpBackend.when('GET', '/githubproxy/org/repo1/refs').respond({ refs: 'ref1' });
      var promise = github.get_refs(repo1);
      $httpBackend.flush();
      var result = resolve_promise(promise);
      expect(result).toEqual({ refs: 'ref1' });
    });

    it('should get refs for an array of repos', function() {
      $httpBackend.when('GET', '/githubproxy/org/repo1/refs').respond({ refs: 'ref1' });
      $httpBackend.when('GET', '/githubproxy/org/repo2/refs').respond({ refs: 'ref2' });
      var promise = github.get_refs(repos);
      $httpBackend.flush();
      var result = resolve_promise(promise);

      expect(result instanceof Array).toEqual(true); // TODO(andersonvom): is there a better way?
      expect(result).toContain({ refs: 'ref1' });
      expect(result).toContain({ refs: 'ref2' });
    });

    it('should handle different ref types', function() {
      $httpBackend.when('GET', '/githubproxy/org/repo1/refs/custom').respond({ custom: 'lorem ispum' });
      var promise = github.get_refs(repo1, 'custom');
      $httpBackend.flush();
      var result = resolve_promise(promise);
      expect(result).toEqual({ custom: 'lorem ispum' });
    });
  });

  describe('#get_tags', function() {
    it('should be a wrapper for #get_refs', function() {
      var repo = { git_refs_url: "http://github.com/org/repo1/refs{/sha}" };
      spyOn(github, 'get_refs');
      github.get_tags(repo);
      expect(github.get_refs).toHaveBeenCalledWith(repo, 'tags');
    });
  });

  describe('get_contents', function(){
    beforeEach(inject(function(github, $http, $injector){
      $httpBackend = $injector.get('$httpBackend');
      this.github = github;
      url = '';
      content_item = '';
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
