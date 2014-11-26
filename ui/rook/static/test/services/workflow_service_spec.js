describe('workflow service', function(){
  var task;
  var workflow;
  beforeEach(module('checkmate.services'));
  beforeEach(inject(['workflow', function(workflow_service){
    workflow = workflow_service;
    task = {};
  }]));

  describe('iconify', function(){
    it('should return fast forward icon for future tasks', function(){
      task = { state: 1 };
      expect(workflow.iconify(task)).toEqual('icon-fast-forward');
    });

    it('should return thumbs up icon for likely tasks', function(){
      task = { state: 2 };
      expect(workflow.iconify(task)).toEqual('icon-thumbs-up');
    });

    it('should return thumbs up icon for maybe tasks', function(){
      task = { state: 4 };
      expect(workflow.iconify(task)).toEqual('icon-hand-right');
    });

    it('should return warning sign icon for waiting tasks with internal failures', function(){
      task = { state: 8,
                   internal_attributes: { task_state: { state: 'FAILURE' } }
                 };
      expect(workflow.iconify(task)).toEqual('icon-warning-sign');
    });

    it('should return pause icon for waiting tasks without failures', function(){
      task = { state: 8 };
      expect(workflow.iconify(task)).toEqual('icon-pause');
    });

    it('should return plus icon for ready tasks', function(){
      task = { state: 16 };
      expect(workflow.iconify(task)).toEqual('icon-plus');
    });

    it('should return remove icon for cancelled tasks', function(){
      task = { state: 32 };
      expect(workflow.iconify(task)).toEqual('icon-remove');
    });

    it('should return ok icon for completed tasks', function(){
      task = { state: 64 };
      expect(workflow.iconify(task)).toEqual('icon-ok');
    });

    it('should return adjust icon for triggered tasks', function(){
      task = { state: 128 };
      expect(workflow.iconify(task)).toEqual('icon-adjust');
    });

    it('should return question icon for tasks with invalid state', function(){
      task = { state: 9001 };
      expect(workflow.iconify(task)).toEqual('icon-question-sign');
    });
  });

  describe('classify', function(){
    it('should append important label for error task', function(){
      task = { state: -1 };
      expect(workflow.classify(task)).toEqual('label label-important');
    });

    it('should not append an additional label for future tasks', function(){
      task = { state: 1 };
      expect(workflow.classify(task)).toEqual('label');
    });

    it('should not append an additional label for likely tasks', function(){
      task = { state: 2 };
      expect(workflow.classify(task)).toEqual('label');
    });

    it('should not append an additional label for maybe tasks', function(){
      task = { state: 4 };
      expect(workflow.classify(task)).toEqual('label');
    });

    it('should append important label for waiting tasks that failed internally', function(){
      task = { state: 8,
                   internal_attributes: { task_state: { state: 'FAILURE' } }
                 };
      expect(workflow.classify(task)).toEqual('label label-important');
    });

    it('should append warning label for waiting tasks without failures', function(){
      task = { state: 8 };
      expect(workflow.classify(task)).toEqual('label label-warning');
    });

    it('should append info label for ready tasks', function(){
      task = { state: 16 };
      expect(workflow.classify(task)).toEqual('label label-info');
    });

    it('should append success label for cancelled tasks', function(){
      task = { state: 32 };
      expect(workflow.classify(task)).toEqual('label label-success');
    });

    it('should append success label for completed tasks', function(){
      task = { state: 64 };
      expect(workflow.classify(task)).toEqual('label label-success');
    });

    it('should not append an additional label for triggered tasks', function(){
      task = { state: 128 };
      expect(workflow.classify(task)).toEqual('label');
    });

    it('should not append an additional label if task is undefined', function(){
      expect(workflow.classify(undefined)).toEqual('label');
    });

    it('should append inverse label if task state is invalid', function(){
      task = { state: 9001 };
      expect(workflow.classify(task)).toEqual('label label-inverse');
    });
  });

  describe('colorize', function(){
    it('should return error alert if future task has an internal failure', function(){
      task = { state: 1,
                   internal_attributes: { task_state: { state: 'FAILURE' } }
                 };
      expect(workflow.colorize(task)).toEqual('alert-error');
    });

    it('should return waiting alert if future task does not have internal failure', function(){
      task = { state: 1 };
      expect(workflow.colorize(task)).toEqual('alert-waiting');
    });

    it('should return error alert if likely task has an internal failure', function(){
      task = { state: 2,
                   internal_attributes: { task_state: { state: 'FAILURE' } }
                 };
      expect(workflow.colorize(task)).toEqual('alert-error');
    });

    it('should return waiting alert if likely task does not have internal failure', function(){
      task = { state: 2 };
      expect(workflow.colorize(task)).toEqual('alert-waiting');
    });

    it('should return error alert if maybe task has an internal failure', function(){
      task = { state: 4,
                   internal_attributes: { task_state: { state: 'FAILURE' } }
                 };
      expect(workflow.colorize(task)).toEqual('alert-error');
    });

    it('should return waiting alert if maybe task does not have internal failure', function(){
      task = { state: 4 };
      expect(workflow.colorize(task)).toEqual('alert-waiting');
    });

    it('should return error alert if waiting task has an internal failure', function(){
      task = { state: 8,
                   internal_attributes: { task_state: { state: 'FAILURE' } }
                 };
      expect(workflow.colorize(task)).toEqual('alert-error');
    });

    it('should return waiting alert if waiting task does not have internal failure', function(){
      task = { state: 8 };
      expect(workflow.colorize(task)).toEqual('alert-waiting');
    });

    it('should return info alert if ready task' , function(){
      task = { state: 16 };
      expect(workflow.colorize(task)).toEqual('alert-info');
    });

    it('should return error alert if cancelled task' , function(){
      task = { state: 32 };
      expect(workflow.colorize(task)).toEqual('alert-error');
    });

    it('should return success alert if completed task' , function(){
      task = { state: 64 };
      expect(workflow.colorize(task)).toEqual('alert-success');
    });

    it('should return info alert if triggered task' , function(){
      task = { state: 128 };
      expect(workflow.colorize(task)).toEqual('alert-info');
    });
  });

  describe('state_name', function(){
    it('should return Error for tasks in error state', function(){
      task = { state: -1 };
      expect(workflow.state_name(task)).toEqual('Error');
    });

    it('should return Future for tasks in future state', function(){
      task = { state: 1 };
      expect(workflow.state_name(task)).toEqual('Future');
    });

    it('should return Likely for tasks in likely state', function(){
      task = { state: 2 };
      expect(workflow.state_name(task)).toEqual('Likely');
    });

    it('should return Maybe for tasks in maybe state', function(){
      task = { state: 4 };
      expect(workflow.state_name(task)).toEqual('Maybe');
    });

    it('should return Failure for tasks with failures', function(){
      task = { state: 8,
                   internal_attributes: { task_state: { state: 'FAILURE' } }
                 };
      expect(workflow.state_name(task)).toEqual('Failure');
    });

    it('should return Waiting for tasks in waiting state', function(){
      task = { state: 8 };
      expect(workflow.state_name(task)).toEqual('Waiting');
    });

    it('should return Ready for tasks in ready state', function(){
      task = { state: 16 };
      expect(workflow.state_name(task)).toEqual('Ready');
    });

    it('should return Cancelled for tasks in cancelled state', function(){
      task = { state: 32 };
      expect(workflow.state_name(task)).toEqual('Cancelled');
    });

    it('should return Completed for tasks in completed state', function(){
      task = { state: 64 };
      expect(workflow.state_name(task)).toEqual('Completed');
    });

    it('should return Triggered for tasks in triggered state', function(){
      task = { state: 128 };
      expect(workflow.state_name(task)).toEqual('Triggered');
    });

    it('should return unknown for tasks in invalid state', function(){
      task = { state: 9001 };
      expect(workflow.state_name(task)).toEqual('unknown');
    });
  });

  describe('calculateStatistics', function(){
    var tasks;
    beforeEach(function(){
      tasks = [];
    });

    describe('totalTime', function(){
      it("should calculate total time using task estimated times", function(){
        tasks = [
          { internal_attributes: { estimated_completed_in: 12 }, state: 16 },
          { internal_attributes: { estimated_completed_in: 10 }, state: 16 },
          { internal_attributes: { estimated_completed_in: 20 }, state: 16 }
        ];
        expect(workflow.calculateStatistics(tasks).totalTime).toEqual(42);
      });

      it('should default estimated time to 10 if task does not have an estimate', function(){
        tasks = [
          { state: 16 },
          { state: 16 },
          { state: 16 }
        ];
        expect(workflow.calculateStatistics(tasks).totalTime).toEqual(30);
      });
    });

    describe('timeRemaining', function(){
      it('should be the total time if no tasks are complete', function(){
        tasks = [
          { internal_attributes: { estimated_completed_in: 12 }, state: 16 },
          { internal_attributes: { estimated_completed_in: 10 }, state: 16 },
          { internal_attributes: { estimated_completed_in: 20 }, state: 16 }
        ];
        expect(workflow.calculateStatistics(tasks).timeRemaining).toEqual(42);
      });

      it('should be the total time minus the complete task estimated times', function(){
        tasks = [
          { internal_attributes: { estimated_completed_in: 12 }, state: 64 },
          { internal_attributes: { estimated_completed_in: 10 }, state: 64 },
          { internal_attributes: { estimated_completed_in: 20 }, state: 16 }
        ];
        expect(workflow.calculateStatistics(tasks).timeRemaining).toEqual(20);
      });

      it('default estimated complete time to 10 if not present', function(){
        tasks = [
          { internal_attributes: {}, state: 64 },
          { internal_attributes: { estimated_completed_in: 10 }, state: 64 },
          { internal_attributes: { estimated_completed_in: 20 }, state: 16 }
        ];
        expect(workflow.calculateStatistics(tasks).timeRemaining).toEqual(20);
      });
    });

    describe('taskStates', function(){
      it('should add up the different state counts', function(){
        tasks = [
          { internal_attributes: { estimated_completed_in: 12 }, state: 2 },
          { internal_attributes: { estimated_completed_in: 10 }, state: 16 },
          { internal_attributes: { estimated_completed_in: 20 }, state: 16 }
        ];
        var expected = {
          future: 0,
          likely: 1,
          maybe: 0,
          waiting: 0,
          ready: 2,
          cancelled: 0,
          completed: 0,
          triggered: 0,
          error: 0
        };
        expect(workflow.calculateStatistics(tasks).taskStates).toEqual(expected);
      });

      it('should add a count to error if a task failed', function(){
        tasks = [
          { internal_attributes: { estimated_completed_in: 12,
                                   task_state: { state: 'FAILURE' } },
            state: 8 }
        ];
        expect(workflow.calculateStatistics(tasks).taskStates.error).toEqual(1);
      });

      it('should add a count to waiting if a task is waiting and hasnt failed', function(){
        tasks = [
          { internal_attributes: { estimated_completed_in: 12,
                                   task_state: { state: 'BATMAN' } },
            state: 8 }
        ];
        expect(workflow.calculateStatistics(tasks).taskStates.waiting).toEqual(1);
        expect(workflow.calculateStatistics(tasks).taskStates.error).toEqual(0);
      });
    });
  });
});
