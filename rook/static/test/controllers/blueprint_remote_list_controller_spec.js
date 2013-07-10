describe('BlueprintRemoteListController', function(){
  var scope,
      controller,
      location,
      routeParams,
      resource,
      http,
      items,
      navbar,
      options,
      workflow,
      github;

  beforeEach(function(){
    scope = { $on: emptyFunction, $watch: emptyFunction };
    controller = {};
    location = {};
    routeParams = {};
    resource = {};
    http = {};
    items = { receive: sinon.stub().returns({}) };
    navbar = { highlight: emptyFunction };
    options = {};
    workflow = {};
    github = { get_contents: emptyFunction };
    localStorage.clear();
  });

  describe('initialization', function(){
    beforeEach(function(){
      controller = new BlueprintRemoteListController(scope, location, routeParams, resource, http, items, navbar, options, workflow, github);
    });

    it('should not display the loading gif', function(){
      expect(scope.loading_remote_blueprints).toBe(false);
    });

    it('should use master as the default branch', function(){
      expect(scope.default_branch).toBe('master');
    });
  });

  describe('receive_blueprints', function(){
    var data;
    beforeEach(function(){
      items.clear = emptyFunction;
      data = undefined;
    });

    it('should remove the loading gif from display', function(){
      scope.loading_remote_blueprints = true;
      controller = new BlueprintRemoteListController(scope, location, routeParams, resource, http, items, navbar, options, workflow, github);
      scope.receive_blueprints();
      expect(scope.loading_remote_blueprints).toBe(false);
    });

    it('should get the checkmate.yaml to check if its a blueprint repo', function(){
      data = { all: [{ api_url: 'https://underpressure.com',
               is_blueprint_repo: false,
               name: 'a'
            }]};
      items = { receive: sinon.stub().returns(data) };

      github = { get_contents: sinon.spy() };
      controller = new BlueprintRemoteListController(scope, location, routeParams, resource, http, items, navbar, options, workflow, github);
      scope.receive_blueprints();
      expect(github.get_contents.getCall(0).args[0]).not.toBeNull();
      expect(github.get_contents.getCall(0).args[1]).toEqual('https://underpressure.com');
      expect(github.get_contents.getCall(0).args[2]).toEqual('checkmate.yaml');
    });

    it('should sort the items by name alphabetically (case insensitive)', function(){
      var abba = { name: 'Abba' };
      var alpha = { name: 'alpha' };
      var arkansas = { name: 'Arkansas' };
      data = { all: [alpha, abba, arkansas]};
      items = { receive: sinon.stub().returns(data) };
      github = { get_contents: sinon.stub().returns(
          { then: sinon.stub().returns( {then: emptyFunction}) }
      ) };
      controller = new BlueprintRemoteListController(scope, location, routeParams, resource, http, items, navbar, options, workflow, github);
      scope.receive_blueprints();
      expect(scope.items).toEqual([abba, alpha, arkansas]);
    });

    it('should chain callback promises when checking blueprint repos instead of sending all http requests at once', function(){
      var alpha = { name: 'Alpha' },
          bravo = { name: 'Bravo' },
          charlie = { name: 'Charlie' },
          bravo_promise = { then: sinon.stub() },
          alpha_promise = { then: sinon.stub().returns(bravo_promise) };

      items.all = [ alpha, bravo, charlie];
      data = { all: [ alpha, bravo, charlie] };
      items = { receive: sinon.stub().returns(data) };
      github = { get_contents: sinon.stub().returns(alpha_promise) };
      controller = new BlueprintRemoteListController(scope, location, routeParams, resource, http, items, navbar, options, workflow, github);
      scope.receive_blueprints();
      expect(github.get_contents).toHaveBeenCalled();
      expect(alpha_promise.then).toHaveBeenCalled();
      expect(bravo_promise.then).toHaveBeenCalled();
    });

    describe('the callback function', function(){
      var success_function, item;
      beforeEach(function(){
        item = { api_url: 'https://underpressure.com', is_blueprint_repo: false, name: 'a' };
        items.all = [item];
        data = { all: [item] };
        items = { receive: sinon.stub().returns(data) };
        github = { get_contents: sinon.spy() };
        controller = new BlueprintRemoteListController(scope, location, routeParams, resource, http, items, navbar, options, workflow, github);
        scope.receive_blueprints();

        success_function = github.get_contents.getCall(0).args[3];
      });

      it('should set is_blueprint_repo to true for item if successfully retrieved a checkmate.yaml file', function(){
        var content_data = { type: 'file' };
        success_function(content_data);
        expect(item.is_blueprint_repo).toBe(true);
      });
    });
  });
});
