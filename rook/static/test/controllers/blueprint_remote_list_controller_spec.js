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
    navbar = { highlight: emptyFunction };
    items = { receive: emptyFunction };
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
    beforeEach(function(){
      items.clear = emptyFunction;
    });

    it('should remove the loading gif from display', function(){
      scope.loading_remote_blueprints = true;
      controller = new BlueprintRemoteListController(scope, location, routeParams, resource, http, items, navbar, options, workflow, github);
      scope.receive_blueprints();
      expect(scope.loading_remote_blueprints).toBe(false);
    });

    it('should get the checkmate.yaml to check if its a blueprint repo', function(){
      items.all = [{ api_url: 'https://underpressure.com',
                     is_blueprint_repo: false
                  }];

      github = { get_contents: sinon.spy() };
      controller = new BlueprintRemoteListController(scope, location, routeParams, resource, http, items, navbar, options, workflow, github);
      scope.receive_blueprints();
      expect(github.get_contents.getCall(0).args[0]).not.toBeNull();
      expect(github.get_contents.getCall(0).args[1]).toEqual('https://underpressure.com');
      expect(github.get_contents.getCall(0).args[2]).toEqual('checkmate.yaml');
    });

    describe('the callback function', function(){
      var success_function, item;
      beforeEach(function(){
        item = { api_url: 'https://underpressure.com', is_blueprint_repo: false };
        items.all = [item];
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
