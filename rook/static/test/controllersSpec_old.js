/*describe('controllers', function() {
  var tasks, scroll, scope;

  beforeEach(module(function($provide) {
    tasks = jasmine.createSpyObj('tasks', ['getTasksFromServer', 'next', 'clearFilter', 'filterBy']);
    scroll = jasmine.createSpyObj('scroll', ['pageDown', 'toCurrent']);

    // mock out services
    $provide.value('tasks', tasks);
    $provide.value('scroll', scroll);
  }));

  beforeEach(inject(function($rootScope) {
    scope = $rootScope;
  }));


  describe('App', function() {
    beforeEach(inject(function($controller) {
      $controller(AppController, {$scope: scope});
    }));


    it('should publish tasks service', function() {
      expect(scope.tasks).toBe(tasks);
    });


    it('should scroll when selectedIdx change to not null value', function() {
      expect(scroll.toCurrent).not.toHaveBeenCalled();

      scope.$apply(function() {
        tasks.selectedIdx = 1;
      });
      expect(scroll.toCurrent).toHaveBeenCalled();
      scroll.toCurrent.reset();

      scope.$apply(function() {
        tasks.selectedIdx = 0;
      });
      expect(scroll.toCurrent).toHaveBeenCalled();
      scroll.toCurrent.reset();

      scope.$apply(function() {
        tasks.selectedIdx = null;
      });
      expect(scroll.toCurrent).not.toHaveBeenCalled();
    });


    describe('refresh', function() {
      it('should call tasks.getTasksFromServer()', function() {
        scope.refresh();
        expect(tasks.getTasksFromServer).toHaveBeenCalled();
        expect(tasks.getTasksFromServer.callCount).toBe(1);
      });
    });


    describe('handleSpace', function() {
      it('should scroll page down', function() {
        scope.handleSpace();
        expect(scroll.pageDown).toHaveBeenCalled();
        expect(scroll.pageDown.callCount).toBe(1);
      });


      it('should call tasks.next() if not scrolled', function() {
        scroll.pageDown.andReturn(false);
        scope.handleSpace();
        expect(tasks.next).toHaveBeenCalled();
        expect(tasks.next.callCount).toBe(1);
      });
    });
  });


  describe('NavBar', function() {
    beforeEach(inject(function($controller) {
      $controller(NavBarController, {$scope: scope});
    }));


    it('should delegate methods to tasks service', function() {
      scope.showAll();
      expect(tasks.clearFilter).toHaveBeenCalled();

      scope.showUnread();
      expect(tasks.filterBy).toHaveBeenCalledWith('read', false);
      tasks.filterBy.reset();

      scope.showRead();
      expect(tasks.filterBy).toHaveBeenCalledWith('read', true);
      tasks.filterBy.reset();

      scope.showStarred();
      expect(tasks.filterBy).toHaveBeenCalledWith('starred', true);
    });
  });
});*/
