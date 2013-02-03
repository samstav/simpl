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
        if (task.state == 8 &&
            'internal_attributes' in  task &&
            'task_state' in task.internal_attributes &&
            task.internal_attributes.task_state.state == 'FAILURE') {
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
      }
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
            break;
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
                label_class += " label-important";
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
              break;
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
            break;
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
            break;
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

/* A collection that holds the data behind a view and controller.
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
      if (transform === null || transform === undefined)
          transform = function(item) {return item;};
      for (var attrname in list) { items.data[attrname] = list[attrname]; }
      angular.forEach(list, function(value, key) {
        this.push(transform(value, key));
      }, items.all);
      items.count = items.all.length;
      items.filtered = items.all;
      console.log('Done receiving ' + items.count + ' entries');
    },

    clear: function() {
      items.data = {};
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


services.value('navbar', {
  highlight: function(menu_name) {
    $(document).ready(function() {
      $('#nav-elements li').removeClass('active');
      $('#nav-' + menu_name).addClass('active');
    });
  }
});

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
      }
    }, 0);
  }
});

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
  },

  substituteVariables: function(source, variables) {
    var text = JSON.stringify(source);
    var changed = false;
    for (var v in variables)
      if (text.indexOf(v)) {
        text = text.replace(v, variables[v]);
        changed = true;
      }
    if (changed) {
      var updated = JSON.parse(text);
      this.mergeInto(source, updated);
    }
  },

  //Merges src into target. Returns target. Modifies target with differences.
  mergeInto: function mergeInto(target, src) {
    var array = Array.isArray(src);
    if (src === null || src === undefined)
      return target;

    if (array) {
        target = target || [];
        src.forEach(function(e, i) {
            if (target.length < i - 1) {
              target.push(e);
            } else {
              if (typeof e === 'object') {
                  mergeInto(target[i], e);
              } else {
                  if (target[i] != e) {
                      target[i] = e;
                  }
              }
            }
        });
    } else {
        if (target && typeof target === 'object') {
            Object.keys(target).forEach(function (key) {
                var val = target[key];
                if (typeof val === 'object') {
                  mergeInto(val, src[key]);
                } else {
                  if (val !== src[key])
                    target[key] = src[key];
                }
            });
        }
        Object.keys(src).forEach(function (key) {
            if (typeof src[key] !== 'object' || !src[key]) {
                if (target[key] != src[key])
                  target[key] = src[key];
            }
            else {
                if (!target[key]) {
                    target[key] = src[key];
                } else {
                    mergeInto(target[key], src[key]);
                }
            }
        });
    }

    return target;
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
});

/* Github APIs for blueprint parsing*/
services.factory('github', ['$http', function($http) {
  var me = {
    //Parse URL and returns the github components (org, user, repo) back
    parse_org_url: function(url, callback) {
      var results = {};
      var u = URI(url);
      var parts = u.path().substring(1).split('/');
      var first_path_part = parts[0];
      results.server = u.protocol() + '://' + u.host(); //includes port
      results.url = u.href();
      results.owner = first_path_part;
      if (parts.length > 1) {
        results.repo = {name: parts[1]};
      } else {
        results.repo = {};
      }
      //Test if org
      $http({method: 'HEAD', url: (checkmate_server_base || '') + '/githubproxy/api/v3/orgs/' + first_path_part,
          headers: {'X-Target-Url': results.server, 'accept': 'application/json'}}).
      success(function(data, status, headers, config) {
        //This is an org
        results.org = first_path_part;
        results.user = null;
        callback();
      }).
      error(function(data, status, headers, config) {
        //This is not an org (assume it is a user)
        results.org = null;
        results.user = first_path_part;
        callback();
      });
      return results;
    },

    //Load all repos for owner
    get_repos: function(remote, callback, error_callback) {
      var path = (checkmate_server_base || '') + '/githubproxy/api/v3/';
      if (remote.org !== null) {
        path += 'orgs/' + remote.org + '/repos';
      } else
        path += 'users/' + remote.user + '/repos';
      console.log("Loading: " + path);
      $http({method: 'GET', url: path, headers: {'X-Target-Url': remote.server, 'accept': 'application/json'}}).
        success(function(data, status, headers, config) {
          console.log("Load repos returned");
          callback(data);
          console.log("Done loading repos");
        }).
        error(function(data, status, headers, config) {
          var response = {data: data, status: status};
          error_callback(response);
        });
    },

    //Load one repo
    get_repo: function(remote, repo_name, callback, error_callback) {
      var path = (checkmate_server_base || '') + '/githubproxy/api/v3/repos/' + remote.owner + '/' + repo_name;
      console.log("Loading: " + path);
      $http({method: 'GET', url: path, headers: {'X-Target-Url': remote.server, 'accept': 'application/json'}}).
        success(function(data, status, headers, config) {
          callback(data);
        }).
        error(function(data, status, headers, config) {
          var response = {data: data, status: status};
          error_callback(response);
        });
    },

    //Get all branches (and tags) for a repo
    get_branches: function(remote, callback, error_callback) {
      $http({method: 'GET', url: (checkmate_server_base || '') + '/githubproxy/api/v3/repos/' + remote.owner + '/' + remote.repo.name + '/git/refs',
          headers: {'X-Target-Url': remote.server, 'accept': 'application/json'}}).
      success(function(data, status, headers, config) {
        //Only branches and tags
        var filtered = _.filter(data, function(item) {
          return item.ref.indexOf('refs/heads/') === 0 || item.ref.indexOf('refs/tags/') === 0;
        });
        //Format the data (we need name, type, and sha only)
        var transformed = _.map(filtered, function(item){
          if (item.ref.indexOf('refs/heads/') === 0)
            return {
              type: 'branch',
              name: item.ref.substring(11),
              commit: item.object.sha
              };
          else if (item.ref.indexOf('refs/tags/') === 0)
            return {
              type: 'tag',
              name: item.ref.substring(10),
              commit: item.object.sha
              };
        });
        callback(transformed);
      }).
      error(function(data, status, headers, config) {
        var response = {data: data, status: status};
        error_callback(response);
      });
    },

    // Get a single branch or tag and return it as an object (with type, name, and commit)
    get_branch_from_name: function(remote, branch_name, callback, error_callback) {
      $http({method: 'GET', url: (checkmate_server_base || '') + '/githubproxy/api/v3/repos/' + remote.owner + '/' + remote.repo.name + '/git/refs',
          headers: {'X-Target-Url': remote.server, 'accept': 'application/json'}}).
      success(function(data, status, headers, config) {
        //Only branches and tags
        var branch_ref = 'refs/heads/' + branch_name;
        var tag_ref = 'refs/tags/' + branch_name;
        var found = _.find(data, function(item) {
          return item.ref == branch_ref || item.ref == tag_ref;
        });
        if (found === undefined) {
          var response = {data: "Branch or tag " + branch_name + " not found", status: "404"};
          error_callback(response);
          return;
        }

        //Format and return the data (we need name, type, and sha only)
        if (found.ref == branch_ref)
          callback({
            type: 'branch',
            name: found.ref.substring(11),
            commit: found.object.sha
            });
        else if (item.ref == tag_ref)
          callback({
            type: 'tag',
            name: found.ref.substring(10),
            commit: found.object.sha
            });
      }).
      error(function(data, status, headers, config) {
        var response = {data: data, status: status};
        error_callback(response);
      });
    },

    get_blueprint: function(remote, username, callback, error_callback) {
      var repo_url = (checkmate_server_base || '') + '/githubproxy/api/v3/repos/' + remote.owner + '/' + remote.repo.name;
      $http({method: 'GET', url: repo_url + '/git/trees/' + remote.branch.commit,
          headers: {'X-Target-Url': remote.server, 'accept': 'application/json'}}).
      success(function(data, status, headers, config) {
        var checkmate_yaml_file = _.find(data.tree, function(file) {return file.path == "checkmate.yaml";});
        if (checkmate_yaml_file === undefined) {
          error_callback("No 'checkmate.yaml' found in the repository '" + remote.repo.name + "'");
        } else {
          $http({method: 'GET', url: repo_url + '/git/blobs/' + checkmate_yaml_file.sha,
              headers: {'X-Target-Url': remote.server, 'Accept': 'application/vnd.github.v3.raw'}}).
          success(function(data, status, headers, config) {
            var checkmate_yaml = {};
            try {
              checkmate_yaml = YAML.parse(data.replace('%repo_url%', remote.repo.git_url + '#' + remote.branch.name).replace('%username%', username || '%username%'));
            } catch(err) {
              if (err.name == "YamlParseException")
                error_callback("YAML syntax error in line " + err.parsedLine + ". '" + err.snippet + "' caused error '" + err.message + "'");
            }
            callback(checkmate_yaml);
          }).
          error(function(data, status, headers, config) {
            var response = {data: data, status: status};
            error_callback(response);
          });
        }
      }).
      error(function(data, status, headers, config) {
        var response = {data: data, status: status};
        error_callback(response);
      });
    }
  };
  return me;
}]);
