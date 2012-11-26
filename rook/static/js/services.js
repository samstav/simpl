var services = angular.module('checkmate.services', []);

/*
 * shared Workflow utilities
**/
services.factory('workflow', [function() {
	var me = {
		// Get all tasks from hierarchy and put them in a flat list
		flattenTasks: function(accumulator, tree) {
                    if (tree !== undefined) {
			accumulator[tree.task_spec] = tree;
			if (tree.children.length > 0) {
			  _.each(tree.children, function(child, index) {
				$.extend(accumulator, me.flattenTasks(accumulator, tree.children[index]));
			  });
			}
                    }
		    return accumulator;
		},
		// Get all tasks with relationships and put them in a collection
		parseTasks: function(tasks, specs) {
                        var jsonTasks = [];
    
                        _.each(tasks, function(task) {
                          var adjacencies = [];
                          _.each(task.children, function(child) {
                                var adj = {
                                  nodeTo: child.task_spec,
                                  nodeFrom: task.task_spec,
                                  data: {}
                                };
                                adjacencies.push(adj);
                          });
                    
                        var t = {
                              id: task.id,
                              name: task.task_spec,
                              description: specs[task.task_spec].description,
                              adjacencies: adjacencies,
                              state_class: me.colorize(task),
                              data: {
                                "$color": "#83548B",
                                "$type": "circle"
                              }
                        };
                        if (task.state == 8
                            && 'internal_attributes' in  task
                            && 'task_state' in task.internal_attributes
                            && task.internal_attributes.task_state.state == 'FAILURE') {
                              t.state = -1;
                        } else
                          t.state = task.state;
                        jsonTasks.push(t);
                    });
		
                    return jsonTasks;
		},
		// Display the workflow
		renderWorkflow: function(container_selector, template_selector, tasks, $scope) {
			var template = $(template_selector).html();
			var container = $(container_selector);
		
			//Clear old data
			d3.selectAll('#rendering').remove();

			for(var i = 0; i < Math.floor(tasks.length/4); i++) {
			  var div = $('<div id="rendering" class="row">');
			  var row = tasks.slice(i*4, (i+1)*4);
			  _.each(row, function(task) {
		
				div.append(Mustache.render(template, task));
			  });
		
			  container.append(div);
			}
		
			$('.task').hover(
			  function() {
				//hover-in
				$(this).addClass('hovering');
				$scope.showConnections($(this));
			  },
			  function() {
				$(this).removeClass('hovering');
				jsPlumb.detachEveryConnection();
			  }
			);
		},
		calculateStatistics: function($scope, tasks) {
		  $scope.totalTime = 0;
		  $scope.timeRemaining  = 0;
		  $scope.taskStates = {
			 future: 0,
			 likely: 0,
			 maybe: 0,
			 waiting: 0,
			 ready: 0,
			 cancelled: 0,
			 completed: 0,
			 triggered: 0,
                         error: 0
		   };
		  _.each(tasks, function(task) {
			if ("internal_attributes" in task && "estimated_completed_in" in task["internal_attributes"]) {
			  $scope.totalTime += parseInt(task["internal_attributes"]["estimated_completed_in"], 10);
			} else {
			  $scope.totalTime += 10;
			};
			switch(parseInt(task.state, 0)) {
			  case -1:
				$scope.taskStates["error"] += 1;
				break;
                          case 1:
				$scope.taskStates["future"] += 1;
				break;
			  case 2:
				$scope.taskStates["likely"] += 1;
				break;
			  case 4:
				$scope.taskStates["maybe"] += 1;
				break;
			  case 8:
                                if ('internal_attributes' in  task && 'task_state' in task.internal_attributes && task.internal_attributes.task_state.state == 'FAILURE')
                                    $scope.taskStates["error"] += 1;
                                else
                                    $scope.taskStates["waiting"] += 1;
				break;
			  case 16:
				$scope.taskStates["ready"] += 1;
				break;
			  case 128:
				$scope.taskStates["triggered"] += 1;
				break;
			  case 32:
				$scope.taskStates["cancelled"] += 1;
				break;
			  case 64:
				$scope.taskStates["completed"] += 1;
				if ("internal_attributes" in task && "estimated_completed_in" in task["internal_attributes"]) {
				  $scope.timeRemaining -= parseInt(task["internal_attributes"]["estimated_completed_in"], 10);
				} else {
				  $scope.timeRemaining -= 10;
				}
				break;
			  default:
				console.log("Invalid state '" + task.state + "'.");
			}
		  });
		  $scope.timeRemaining += $scope.totalTime;
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
		iconify: function(task) {
		  switch(parseInt(task.state, 0)) {
			case 1: //FUTURE
			  return "icon-fast-forward";
			case 2: //LIKELY
			  return "icon-thumbs-up";
			case 4: //MAYBE
			  return "icon-hand-right";
			case 8: //WAITING
                            if ('internal_attributes' in  task && 'task_state' in task.internal_attributes && task.internal_attributes.task_state.state == 'FAILURE')
                                return "icon-warning-sign";
                            else
                                return "icon-pause";
			case 16: //READY
			  return "icon-plus";
			case 32: //CANCELLED
			  return "icon-remove";
			case 64: //COMPLETED
			  return "icon-ok";
			case 128: //TRIGGERED
			  return "icon-adjust";
			default:
			  console.log("Invalid state '" + state + "'.");
			  return "icon-question-sign";
		  }
		},
		classify: function(task) {
		  var label_class = "label";
		  if (typeof task != 'undefined') {
		      switch(parseInt(task.state, 0)) {
			case -1:
			    label_class += " label-important";
                            break;
			case 1:
			case 2:
			case 4:
                            break;
			case 8:
			    if ('internal_attributes' in  task && 'task_state' in task.internal_attributes && task.internal_attributes.task_state.state == 'FAILURE')
				label_class += " label-important"
			    else
				label_class += " label-warning";
                            break;
			case 16:
			    label_class += " label-info";
                            break;
			case 32:
			case 64:
			    label_class += " label-success";
                            break;
			case 128:
			default:
			  console.log("Invalid task state '" + task.state + "'.");
			  label_class += " label-inverse";
			}
		  }
		  return label_class;
		},
		/**
		 *  See above.
		 */
		colorize: function(task) {
		  switch(task.state) {
			case 1:
			case 2:
			case 4:
			case 8:
			    if ('internal_attributes' in  task && 'task_state' in task.internal_attributes && task.internal_attributes.task_state.state == 'FAILURE')
				return "alert-error";
			    else
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
			  return "unknown";
		  }
		},
		state_name: function(task) {
		  switch(task.state) {
			case -1:
				return "Error";
			case 1:
				return "Future";
			case 2:
				return "Likely";
			case 4:
				return "Maybe";
			case 8:
			case 8:
			    if ('internal_attributes' in  task && 'task_state' in task.internal_attributes && task.internal_attributes.task_state.state == 'FAILURE')
				return "Failure";
			    else
				return "Waiting";
			case 16:
				return "Ready";
			case 128:
				return "Triggered";
			case 32:
				return "Cancelled";
			case 64:
				return "Completed";
			default:
				console.log("Invalid state '" + state + "'.");
				return "unknown";
		  }
		}
	};

	return me;
}]);

/* A collection the holds the data behind the a view and controller.
 * Used in most controllers
**/
services.factory('items', [ 'filterFilter', function($resource, filter) {
	var items = {
	  data: {},  //original json
	  all: [],  //array of items
	  filtered: [],
	  selected: null,  //selected item
	  selectedIdx: null,  //array index of selected items
	  count: 0,

	  receive: function(list, transform) {
		  console.log("Receiving");
		  if (transform === null | transform == undefined)
			  transform = function(item) {return item;};
		  items.data = list;
		  angular.forEach(list, function(value, key) {
			this.push(transform(value, key));
		  }, items.all);
		  items.count = items.all.length;
		  items.filtered = items.all;
		  console.log('Done receiving ' + items.count + ' entries');
		},

	  clear: function() {
	    items.data = null;
	    items.all = [];
	    items.filtered = [];
	    items.selected = null;
	    items.selectedIdx = null;
	    items.count = 0;
	  },

	  prev: function() {
	  	if (items.hasPrev()) {
	  		items.selectItem(items.selected ? items.selectedIdx - 1 : 0);
	  	}
	  },


	  next: function() {
	  	if (items.hasNext()) {
	  		items.selectItem(items.selected ? items.selectedIdx + 1 : 0);
	  	}
	  },


	  hasPrev: function() {
	    if (!items.selected) {
	      return true;
	    }
	    return items.selectedIdx > 0;
	  },


	  hasNext: function() {
	    if (!items.selected) {
	      return true;
	    }
	    return items.selectedIdx < items.filtered.length - 1;
	  },

	  

	  selectItem: function(idx) {
	    // Unselect previous selection.
	    if (items.selected) {
	      items.selected.selected = false;
	    }

	    items.selected = items.filtered[idx];
	    items.selectedIdx = idx;
	    items.selected.selected = true;

	  },

	  
	  filterBy: function(key, value) {
		console.log('Filtering');
	    items.filtered = filter(items.all, function(item) {
	      return item[key] === value;
	    });
	    items.reindexSelectedItem();
	  },


	  clearFilter: function() {
	  	items.filtered = items.all;
	  	items.reindexSelectedItem();
	  },


	  reindexSelectedItem: function() {
	  	if (items.selected) {
	  		var idx = items.filtered.indexOf(items.selected);

	  		if (idx === -1) {
	  			if (items.selected) items.selected.selected = false;

	  			items.selected = null;
	  			items.selectedIdx = null;
	  		} else {
	  			items.selectedIdx = idx;
	  		}
	  	}
	  }
	};

	return items;
}]);

// Create or open the data store where objects are stored for offline use
services.factory('store', function() {
	return new Lawnchair({
	  name: 'entries',
	  record: 'entry',
	  adapter: 'indexed-db'
	}, function() {
	  //TODO: this should probably go in the item store
	  this.toggleRead = function(key, value) {
	    this.get(key, function(entry) {
		  entry.read = value;
	      this.save(entry);
	    });
	  };

	  //TODO: this should probably go in the item store
	  this.toggleStar = function(key, value) {
	    this.get(key, function(entry) {
	      entry.starred = value;
	      this.save(entry);
	    });
	  };
	});
});

services.factory('old_items', ['$http', 'store', 'filterFilter', function($http, store, filter) {
	var items = {
	  all: [],
	  filtered: [],
	  selected: null,
	  selectedIdx: null,

	  addItem: function(item) {
		  // It's already in the data controller, so we won't re-add it.
		  if (items.all.some(function(val) {
			  return val.item_id == item.item_id;
		  })) return false;

	    // If no results are returned, we insert the new item into the data
	    // controller in order of publication date
	    items.all.push(item);
	    return true;
	  },


	  getItemsFromDataStore: function() {
	    // Get all items from the local data store.
	    // We're using store.all because store.each returns async, and the
	    // method will return before we've pulled all the items out.  Then
	    // there is a strong likelihood of getItemsFromServer stomping on
	    // local items.
	    store.all(function(arr) {
		  arr.forEach(function(entry) {
	        var item = new Item();
	        angular.extend(item, entry);
	        items.addItem(item);
	      });

	      console.log("Entries loaded from local data store:", arr.length);

	      // Load items from the server after we've loaded everything from the local
	      // data store.
	      items.getItemsFromServer();
	    });
	  },


	  getItemsFromServer: function() {
	    var feedURL = 'http://blog.chromium.org/feeds/posts/default?alt=json';

	    var successCallback = function(data, status, headers, config) {
	      items.all = [];

	      // Iterate through the items and create a new JSON object for each item
	      data.feed.entry.forEach(function(entry) {
	      	var item = new Item(entry, data.feed.title.$t, getLink(data.feed.link, 'alternate'));

	        // Try to add the item to the data controller, if it's successfully
	        //  added, we get TRUE and add the item to the local data store,
	        //  otherwise it's likely already in the local data store.
	        if (items.addItem(item)) {
	          store.save(angular.copy(item));
	        }
	      });

	      items.filtered = items.all;

	      console.log('Entries loaded from server:', items.all.length);
	    };


	    $http.jsonp(feedURL + '&callback=JSON_CALLBACK').success(successCallback);
	    //$http.get(feedURL).success(successCallback).error(errorCallback);
	  },


	  prev: function() {
	  	if (items.hasPrev()) {
	  		items.selectItem(items.selected ? items.selectedIdx - 1 : 0);
	  	}
	  },


	  next: function() {
	  	if (items.hasNext()) {
	  		items.selectItem(items.selected ? items.selectedIdx + 1 : 0);
	  	}
	  },


	  hasPrev: function() {
	    if (!items.selected) {
	      return true;
	    }
	    return items.selectedIdx > 0;
	  },


	  hasNext: function() {
	    if (!items.selected) {
	      return true;
	    }
	    return items.selectedIdx < items.filtered.length - 1;
	  },

	  

	  selectItem: function(idx) {
	    // Unselect previous selection.
	    if (items.selected) {
	      items.selected.selected = false;
	    }

	    items.selected = items.filtered[idx];
	    items.selectedIdx = idx;
	    items.selected.selected = true;

	    items.toggleRead(true);
	  },


	  toggleRead: function(opt_read) {
	    var item = items.selected;
	    var read = opt_read || !item.read;

	    item.read = read;
	    store.toggleRead(item.item_id, read);
	  },


	  toggleStar: function(opt_star) {
	    var item = items.selected;
	    var star = opt_star || !item.starred;

	    item.starred = star;
	    store.toggleStar(item.item_id, star);
	  },


	  markAllRead: function() {
	    items.filtered.forEach(function(item) {
	      item.read = true;
	      store.toggleRead(item.item_id, true);
	    });
	  },


	  filterBy: function(key, value) {
	    items.filtered = filter(items.all, function(item) {
	      return item[key] === value;
	    });
	    items.reindexSelectedItem();
	  },


	  clearFilter: function() {
	  	items.filtered = items.all;
	  	items.reindexSelectedItem();
	  },


	  reindexSelectedItem: function() {
	  	if (items.selected) {
	  		var idx = items.filtered.indexOf(items.selected);

	  		if (idx === -1) {
	  			if (items.selected) items.selected.selected = false;

	  			items.selected = null;
	  			items.selectedIdx = null;
	  		} else {
	  			items.selectedIdx = idx;
	  		}
	  	}
	  },


	  allCount: function() {
	  	return items.all.length;
	  },


	  readCount: function() {
	  	return items.all.filter(function(val, i) { return val.read }).length;
	  },


	  unreadCount: function() {
	  	return items.all.length - items.readCount();
	  },


	  starredCount: function() {
	  	return items.all.filter(function(val, i) { return val.starred }).length;
	  }
	};

	items.getItemsFromDataStore();
	return items;
}]);

services.value('navbar', {
	highlight: function(menu_name) {
		$(document).ready(function() {
			$('#nav-elements li').removeClass('active');
			$('#nav-' + menu_name).addClass('active');
		});
	}
})

services.value('scroll', {
	pageDown: function() {
	  var itemHeight = $('.entry.active').height() + 60;
	  var winHeight = $(window).height();
	  var curScroll = $('.entries').scrollTop();
	  var scroll = curScroll + winHeight;

	  if (scroll < itemHeight) {
	  	$('.entries').scrollTop(scroll);
	  	return true;
	  }

	  // already at the bottom
	  return false;
	},

	toCurrent: function() {
		// Need the setTimeout to prevent race condition with item being selected.
		window.setTimeout(function() {
      var curScrollPos = $('.summaries').scrollTop();
	  var item = $('.summary.active').offset();
	  if (item !== null) {
		var itemTop = item.top - 60;
		$('.summaries').animate({'scrollTop': curScrollPos + itemTop}, 200);
	  };
    }, 0);
	}
})

services.value('settings', {
  getSettingsFromBlueprint: function(blueprint) {
    var options = []; // The accumulating array

    var opts = blueprint.options;
    _.each(opts, function(option, key) {
      options.push($.extend({
        id: key
      }, option));
    });

    _.each(options, function(option) {
      if (option.regex) {
        if (!_.isRegExp(option.regex)) {
          console.log("Regex '" + option.regex + "' is invalid for setting " + option.id);
          delete option["regex"];
        }
      }
    });

    return options;
  },

  getSettingsFromEnvironment: function(env) {
    var options = [];
    return options;
  }
});

// Captures HTTP requests and responses (including errors)
services.config(function ($httpProvider) {
        $httpProvider.responseInterceptors.push('myHttpInterceptor');
        var startFunction = function (data, headersGetter) {
            console.log('Started call');
			if ('requests' in checkmate) {
				checkmate.requests += 1;
			} else
				checkmate.requests = 1;
			$('#loading').attr('src', '/img/ajax-loader-white.gif');
            return data;
        };
        $httpProvider.defaults.transformRequest.push(startFunction);
    })
    // register the interceptor as a service, intercepts ALL angular ajax http calls
    .factory('myHttpInterceptor', function ($q, $window, $rootScope) {
        return function (promise) {
            return promise.then(function (response) {
	            console.log('Call ended successfully');
				checkmate.requests -= 1;
				if (checkmate.requests <= 0)
                			$('#loading').attr('src', '/img/blank.gif');
                return response;
            }, function (response) {
				checkmate.requests -= 1;
				if (checkmate.requests <= 0)
                                    $('#loading').attr('src', '/img/blank.gif');
                return $q.reject(response);
            });
        };
    })



/*
 * support functions
 */
function getLink(links, rel) {
  for (var i = 0, link; link = links[i]; ++i) {
    if (link.rel === rel) {
      return link.href;
    }
  }
  return null;
};

function Item(entry, pub_name, feed_link) {
  this.selected = false;

  // parse the entry from JSON
  if (entry) {
	this.name = entry.name;
	this.id = entry.id.$t;
	this.created = new Date(entry.created);
	this.item_link = getLink(entry.link, 'alternate');
	this.feed_link = feed_link;
	this.content = entry.content.$t;
	this.short_desc = this.content.substr(0, 128) + '...';
  }
}

function OldItem(entry, pub_name, feed_link) {
  this.read = false;
  this.starred = false;
  this.selected = false;

  // parse the entry from JSON
  if (entry) {
		this.title = entry.title.$t;
	  this.item_id = entry.id.$t;
	  this.key = this.item_id; // For LawnChair.
	  this.pub_name = pub_name; // Set the pub name to the feed's title.
	  this.pub_author = entry.author[0].name.$t;
	  this.pub_date = new Date(entry.published.$t);
	  this.item_link = getLink(entry.link, 'alternate');
	  this.feed_link = feed_link;
	  this.content = entry.content.$t;
	  this.short_desc = this.content.substr(0, 128) + '...';
  }
}
