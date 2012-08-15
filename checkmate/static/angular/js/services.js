var services = angular.module('checkmateServices', ['ngResource', 'ngCookies']);

function Task(entry, pub_name, feed_link) {
  this.read = false;
  this.starred = false;
  this.selected = false;

  // parse the entry from JSON
  if (entry) {
		this.title = entry.title.$t;
	  this.task_id = entry.id.$t;
	  this.key = this.task_id; // For LawnChair.
	  this.pub_name = pub_name; // Set the pub name to the feed's title.
	  this.pub_author = entry.author[0].name.$t;
	  this.pub_date = new Date(entry.published.$t);
	  this.task_link = getLink(entry.link, 'alternate');
	  this.feed_link = feed_link;
	  this.content = entry.content.$t;
	  this.short_desc = this.content.substr(0, 128) + '...';
  }
}

// Create or open the data store where objects are stored for offline use
services.factory('cm2', function() {
    var cm = {
      serviceCatalog: null,
      auth: {
      
        setServiceCatalog: function (sc) {
          cm.serviceCatalog = sc;
        },
      
        getToken: function () {
          if (cm.serviceCatalog === null) {
            return null;
          }
      
          return cm.serviceCatalog.access.token.id;
        },
      
        getTenant: function () {
          if (cm.serviceCatalog === null) {
            return null;
          }
      
          return cm.serviceCatalog.access.token.tenant.id;
        },
      
        getUsername: function () {
          if (cm.serviceCatalog === null) {
            return null;
          }
      
          return cm.serviceCatalog.access.user.name;
        },
      
        isAuthenticated: function () {
          if (cm.serviceCatalog === null) {
            return false;
          }
      
          var expires = new Date(cm.serviceCatalog.access.token.expires);
          var now = new Date();
      
          if (expires < now) {
            return false;
          }
      
          return true;
        },
      
      },
      Resource: {
            query: function($http, resource) {
                return $http({
                  method: 'GET',
                  url: tenantUri() + resource,
                  headers: getHeaders()
                });
              },
            
              get: function($http, resource, id) {
                return $http({
                  method: 'GET',
                  url: tenantUri() + resource + '/' + id,
                  headers: getHeaders()
                });
              },
            
              saveOrUpdate: function($http, resource, instance) {
                if (instance.id) {
                  return $http({
                    method: 'PUT',
                    url: tenantUri() + resource + '/' + instance.id,
                    headers: getHeaders(),
                    data: JSON.stringify(instance)
                  });
                } else {
                  return $http({
                    method: 'POST',
                    url: tenantUri() + resource,
                    headers: getHeaders(),
                    data: JSON.stringify(instance)
                  });
                }
              },
            
              del: function($http, resource, instance) {
                return $http({
                  method: 'DELETE',
                  url: tenantId() + resource + '/' + instance.id,
                  headers: getHeaders()
                });
              }
            }
        }
    // Privates
  
    function tenantUri() {
      tenant = cm.auth.getTenant();
      if (tenant !== null) {
        tenant = '/' + tenant + '/';
      } else {
        tenant = '/';
      }
      return tenant;
    }
  
    function getHeaders() {
        return {
          "X-Auth-Token": cm.auth.getToken()
        };
    }
  return cm;
});

services.factory('tasks', ['$http', 'cm2', 'filterFilter', function($http, server, filter) {
	var tasks = {
		all: [],
		filtered: [],
		selected: null,
		selectedIdx: null,


		addTask: function(task) {
			// It's already in the data controller, so we won't re-add it.
			if (tasks.all.some(function(val) {
				return val.task_id == task.task_id;
			})) return false;

		  // If no results are returned, we insert the new task into the data
		  // controller in order of publication date
		  tasks.all.push(task);
		  return true;
		},

	  getTasksFromServer: function(cm) {
	    var successCallback = function(data, status, headers, config) {
	      tasks.all = [];

          //Get all tasks
          tasks.sub_tasks = tasks.flattenTasks({}, data.task_tree);
      
          //Get tasks by spec
          tasks.all = tasks.groupTasks(data.wf_spec.task_specs, tasks.sub_tasks);


	      tasks.filtered = tasks.all;

	      console.log('Entries loaded from server:', tasks.all.length);
	    };


	    cm.Resource.get($http, 'workflows', '2a8d40c593e34520900b3f67e49bd233')
            .success(successCallback).error(function(data, status, headers, config) {
        console.log("Error " + status + " creating new deployment.");
        console.log(deployment);

        //TODO: Need to slice out the data we are interested in.
        $scope.error = data;
        $('#error_modal').modal('show');
      });
	  },


    flattenTasks: function(accumulator, tree) {
      accumulator[tree.id] = tree;
  
      if (tree.children.length > 0) {
        _.each(tree.children, function(child, index) {
          tasks.flattenTasks(accumulator, tree.children[index]);
        });
      }
  
      return accumulator;
    },
  
    groupTasks: function(specs, sub_tasks) {
      var groups = {};
      for (var key in specs) {
        var spec = specs[key];
        groups[spec.name] = {spec: spec, elements: {}, state: null};
      }
  
      for (var key in sub_tasks) {
        var task = sub_tasks[key];
        groups[task.task_spec].elements[key] = {
          task: task,
          state: tasks.colorize(task.state)
          };
        groups[task.task_spec].state = tasks.colorize(task.state);
      }
  
      return groups;
    },
  
    /**
     *  FUTURE    =   1
     *  LIKELY    =   2
     *  MAYBE     =   4
     *  WAITING   =   8
     *  READY     =  16
     *  CANCELLED =  32
     *  COMPLETED =  64
     *  TRIGGERED = 128
     *
     *  TODO: This will be fixed in the API, see:
     *    https://github.rackspace.com/checkmate/checkmate/issues/45
     */
    iconify: function(state) {
      switch(state) {
        case 1:
          return "icon-fast-forward";
        case 2:
          return "icon-thumbs-up";
        case 4:
          return "icon-hand-right";
        case 8:
          return "icon-pause";
        case 16:
          return "icon-plus";
        case 32:
          return "icon-remove";
        case 64:
          return "icon-ok";
        case 128:
          return "icon-adjust";
        default:
          console.log("Invalid state '" + state + "'.");
          return "icon-question-sign";
      }
    },
  
    /**
     *  See above.
     *
     */
    colorize: function(state) {
      switch(state) {
        case 1:
        case 2:
        case 4:
        case 8:
          return "alert-waiting";
        case 16:
        case 128:
          return "alert-info";
        case 32:
          return "alert-error";
        case 64:
          return "alert-success";
        default:
          console.log("Invalid state '" + state + "'.");
          return "unkonwn";
      }
    },


	  prev: function() {
	  	if (tasks.hasPrev()) {
	  		tasks.selectItem(tasks.selected ? tasks.selectedIdx - 1 : 0);
	  	}
	  },


	  next: function() {
	  	if (tasks.hasNext()) {
	  		tasks.selectItem(tasks.selected ? tasks.selectedIdx + 1 : 0);
	  	}
	  },


	  hasPrev: function() {
	    if (!tasks.selected) {
	      return true;
	    }
	    return tasks.selectedIdx > 0;
	  },


	  hasNext: function() {
	    if (!tasks.selected) {
	      return true;
	    }
	    return tasks.selectedIdx < tasks.filtered.length - 1;
	  },


	  selectItem: function(idx) {
	    // Unselect previous selection.
	    if (tasks.selected) {
	      tasks.selected.selected = false;
	    }

    	tasks.selected = tasks.filtered[idx];
    	tasks.selectedIdx = idx;
    	tasks.selected.selected = true;

	    tasks.toggleRead(true);
	  },


	  toggleRead: function(opt_read) {
	    var task = tasks.selected;
	    var read = opt_read || !task.read;

	    task.read = read;
	    store.toggleRead(task.task_id, read);
	  },


	  toggleStar: function(opt_star) {
	    var task = tasks.selected;
	    var star = opt_star || !task.starred;

	    task.starred = star;
	    store.toggleStar(task.task_id, star);
	  },


	  markAllRead: function() {
	  	tasks.filtered.forEach(function(task) {
	      task.read = true;
	      store.toggleRead(task.task_id, true);
	    });
	  },


	  filterBy: function(key, value) {
	    tasks.filtered = filter(tasks.all, function(task) {
	      return task[key] === value;
	    });
	    tasks.reindexSelectedItem();
	  },


	  clearFilter: function() {
	  	tasks.filtered = tasks.all;
	  	tasks.reindexSelectedItem();
	  },


	  reindexSelectedItem: function() {
	  	if (tasks.selected) {
	  		var idx = tasks.filtered.indexOf(tasks.selected);

	  		if (idx === -1) {
	  			if (tasks.selected) tasks.selected.selected = false;

	  			tasks.selected = null;
	  			tasks.selectedIdx = null;
	  		} else {
	  			tasks.selectedIdx = idx;
	  		}
	  	}
	  },

      

	  allCount: function() {
	  	return tasks.all.length;
	  },


	  readCount: function() {
	  	return tasks.all.filter(function(val, i) { return val.read }).length;
	  },


	  unreadCount: function() {
	  	return tasks.all.length - tasks.readCount();
	  },


	  starredCount: function() {
	  	return tasks.all.filter(function(val, i) { return val.starred }).length;
	  }
	};

	tasks.getTasksFromServer(server);
	return tasks;
}]);