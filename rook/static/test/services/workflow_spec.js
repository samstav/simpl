describe('workflow', function(){
  beforeEach(module('checkmate.services'));
  beforeEach(inject(function(workflow){
    this.workflow = workflow;
  }));

  it('should append important label for -1', function(){
    var task = { state: -1 };
    expect(this.workflow.classify(task)).toEqual('label label-important');
  });

  it('should not append an additional label for 1', function(){
    var task = { state: 1 };
    expect(this.workflow.classify(task)).toEqual('label');
  });

  it('should not append an additional label for 2', function(){
    var task = { state: 2 };
    expect(this.workflow.classify(task)).toEqual('label');
  });

  it('should not append an additional label for 4', function(){
    var task = { state: 4 };
    expect(this.workflow.classify(task)).toEqual('label');
  });

  it('should append important label for 8 if task failed', function(){
    var task = { state: 8,
                 internal_attributes: { task_state: { state: 'FAILURE' } }
               };
    expect(this.workflow.classify(task)).toEqual('label label-important');
  });

  it('should append warning label for 8 if task did not fail', function(){
    var task = { state: 8 };
    expect(this.workflow.classify(task)).toEqual('label label-warning');
  });

  it('should append info label for 16', function(){
    var task = { state: 16 };
    expect(this.workflow.classify(task)).toEqual('label label-info');
  });

  it('should append success label for 32', function(){
    var task = { state: 32 };
    expect(this.workflow.classify(task)).toEqual('label label-success');
  });

  it('should append success label for 64', function(){
    var task = { state: 64 };
    expect(this.workflow.classify(task)).toEqual('label label-success');
  });

  it('should not append an additional label for 128', function(){
    var task = { state: 128 };
    expect(this.workflow.classify(task)).toEqual('label');
  });

  it('should not append an additional label if task is undefined', function(){
    expect(this.workflow.classify(undefined)).toEqual('label');
  });

  it('should append inverse label if task state is invalid', function(){
    var task = { state: 9001 };
    expect(this.workflow.classify(task)).toEqual('label label-inverse');
  });
});
