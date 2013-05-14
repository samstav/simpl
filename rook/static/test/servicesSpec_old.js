/*describe('services', function() {
  beforeEach(module('checkmate.services'));

  describe('tasks', function() {
    var URL = 'http://blog.chromium.org/feeds/posts/default?alt=json&callback=JSON_CALLBACK';
    var tasks;

    beforeEach(module(function($provide) {
      // mock out the store
      $provide.value('store', {
        all: function(callback) {callback([]);},
        save: angular.noop,
        toggleRead: angular.noop,
        toggleStar: angular.noop
      });
    }));

    beforeEach(inject(function($httpBackend, $injector) {
      $httpBackend.whenJSONP(URL).respond(RESPONSE);
      tasks = $injector.get('tasks');

      $httpBackend.flush();
    }));


    describe('addTask', function() {
      it('should only add task if it is not present yet', function() {
        expect(tasks.all.length).toBe(25);

        // returns true if added
        expect(tasks.addTask({task_id: 'fake-id'})).toBe(true);
        expect(tasks.all.length).toBe(26);

        // returns false if not added
        expect(tasks.addTask({task_id: 'fake-id'})).toBe(false);
        expect(tasks.all.length).toBe(26);
      });
    });


    describe('toggleRead', function() {
      it('should toggle selected task read', function() {
        tasks.selectTask(0);
        expect(tasks.filtered[0].read).toBe(true);

        tasks.toggleRead();
        expect(tasks.filtered[0].read).toBe(false);

        tasks.toggleRead();
        expect(tasks.filtered[0].read).toBe(true);
      });


      it('should set read of selected task to given value', function() {
        tasks.selectTask(0);
        expect(tasks.filtered[0].read).toBe(true);

        tasks.toggleRead(true);
        expect(tasks.filtered[0].read).toBe(true);

        tasks.toggleRead(true);
        expect(tasks.filtered[0].read).toBe(true);
      });
    });


    describe('toggleStar', function() {
      it('should toggle selected task star', function() {
        tasks.selectTask(0);
        expect(tasks.filtered[0].starred).toBe(false);

        tasks.toggleStar();
        expect(tasks.filtered[0].starred).toBe(true);

        tasks.toggleStar();
        expect(tasks.filtered[0].starred).toBe(false);
      });


      it('should set starred of selected task to given value', function() {
        tasks.selectTask(0);
        expect(tasks.filtered[0].starred).toBe(false);

        tasks.toggleStar(true);
        expect(tasks.filtered[0].starred).toBe(true);

        tasks.toggleStar(true);
        expect(tasks.filtered[0].starred).toBe(true);
      });
    });


    describe('selectTask', function() {
      it('should select given task', function() {
        tasks.selectTask(1);

        expect(tasks.selected).toBe(tasks.filtered[1]);
        expect(tasks.selectedIdx).toBe(1);
        expect(tasks.filtered[1].selected).toBe(true);
      });


      it('should deselect the previous task', function() {
        tasks.selectTask(1);
        tasks.selectTask(2);

        expect(tasks.filtered[1].selected).toBe(false);
      });


      it('should the task to be read', function() {
        tasks.selectTask(3);

        expect(tasks.filtered[3].read).toBe(true);
      });
    });


    describe('markAllRead', function() {
      it('should set all filtered tasks read', function() {
        tasks.markAllRead();

        angular.forEach(tasks.filtered, function(task) {
          expect(task.read).toBe(true);
        });
      });
    });


    describe('filterBy', function() {
      it('should filter starred/unstarred', function() {
        tasks.filterBy('starred', true);
        expect(tasks.filtered.length).toBe(0);

        tasks.filterBy('starred', false);
        expect(tasks.filtered.length).toBe(25);

        tasks.selectTask(0);
        tasks.toggleStar(true);
        tasks.selectTask(1);
        tasks.toggleStar(true);

        tasks.filterBy('starred', true);
        expect(tasks.filtered.length).toBe(2);

        tasks.filterBy('starred', false);
        expect(tasks.filtered.length).toBe(23);
      });


      it('should update index of selected task', function() {
        tasks.selectTask(1);
        tasks.toggleStar(true);
        expect(tasks.selectedIdx).toBe(1);

        tasks.filterBy('starred', true);
        expect(tasks.selectedIdx).toBe(0);
      });


      it('should remove selected task if not present in new filter', function() {
        var selectedTask = tasks.filtered[2];

        tasks.selectTask(2);
        tasks.toggleRead(true);
        expect(tasks.selectedIdx).toBe(2);

        tasks.filterBy('read', false);
        expect(tasks.selectedIdx).toBe(null);
        expect(tasks.selected).toBe(null);

        // should de-select the previous
        expect(selectedTask.selected).toBe(false);
      });
    });


    describe('clearFilter', function() {
      it('should clear the filters', function() {
        tasks.filterBy('read', true);
        expect(tasks.filtered.length).toBe(0);

        tasks.clearFilter();
        expect(tasks.filtered.length).toBe(25);
      });
    });


    describe('prev', function() {
      it('should select the first task if nothing selected yet', function() {
        tasks.prev();
        expect(tasks.selectedIdx).toBe(0);
      });


      it('should select previous task', function() {
        tasks.selectTask(2);
        tasks.prev();
        expect(tasks.selectedIdx).toBe(1);
      });


      it('should do nothing if first task selected', function() {
        tasks.selectTask(0);
        tasks.prev();
        expect(tasks.selectedIdx).toBe(0);
      });
    });


    describe('next', function() {
      it('should select the first task if nothing selected yet', function() {
        tasks.next();
        expect(tasks.selectedIdx).toBe(0);
      });


      it('should select next task', function() {
        tasks.selectTask(2);
        tasks.next();
        expect(tasks.selectedIdx).toBe(3);
      });


      it('should do nothing if last task selected', function() {
        tasks.selectTask(24);
        tasks.next();
        expect(tasks.selectedIdx).toBe(24);
      });
    });


    describe('hasPrev', function() {
      it('should return true if non first task selected', function() {
        tasks.selectTask(0);
        expect(tasks.hasPrev()).toBe(false);

        tasks.selectTask(1);
        expect(tasks.hasPrev()).toBe(true);

        tasks.selectTask(20);
        expect(tasks.hasPrev()).toBe(true);
      });


      it('should return true if nothing selected yet', function() {
        expect(tasks.hasPrev()).toBe(true);
      });
    });


    describe('hasNext', function() {
      it('should return true if non last task selected', function() {
        tasks.selectTask(0);
        expect(tasks.hasNext()).toBe(true);

        tasks.selectTask(23);
        expect(tasks.hasNext()).toBe(true);

        tasks.selectTask(24);
        expect(tasks.hasNext()).toBe(false);
      });


      it('should return true if nothing selected yet', function() {
        expect(tasks.hasNext()).toBe(true);
      });
    });
  });


  describe('Task', function() {
    var ENTRY = RESPONSE.feed.entry[0];

    it('should parse entry object', function() {
      var task = new Task(ENTRY, 'pub_name', 'link');

      expect(task.read).toBe(false);
      expect(task.starred).toBe(false);
      expect(task.selected).toBe(false);

      expect(task.title).toBe('Connect with Web Intents');
      expect(task.task_id).toBe('tag:blogger.com,1999:blog-2471378914199150966.post-9024980817440542046');
      expect(task.key).toBe('tag:blogger.com,1999:blog-2471378914199150966.post-9024980817440542046');
      expect(task.pub_name).toBe('pub_name');
      expect(task.pub_author).toBe('Google Chrome Blog');
      expect(task.pub_date instanceof Date).toBe(true);
      expect(task.pub_date.getTime()).toBe(1337114100001);
      expect(task.task_link).toEqual('http://blog.chromium.org/2012/05/connect-with-web-intents.html');
      expect(task.feed_link).toBe('link');
    });


    it('should init empty object if no entry given', function() {
      var task = new Task();

      expect(task.read).toBe(false);
      expect(task.starred).toBe(false);
      expect(task.selected).toBe(false);
    });
  });
});*/
