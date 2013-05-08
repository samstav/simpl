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

services.value('options', {
  getOptionsFromBlueprint: function(blueprint) {
    var options = []; // The accumulating array
    var groups = {}; // The options grouped by groups in display-hints
    var region_option = null; // The option identified as the deployment region

    var opts = blueprint.options;
    _.each(opts, function(item, key) {
      // Make a copy and add the ID to it
      var option = $.extend(true, {
        id: key
      }, item);
      options.push(option);

      var dh = option['display-hints'];
      // Guess region option for legacy compatibility
      if (region_option === null && (key == 'region' || option['type'] == 'region') && dh === undefined)
        region_option = option;

      var group;
      if (dh !== undefined) {
        option.order = dh.order || 'XXX';
        if ('group' in dh) {
          group = dh.group;
          // Detect region (overrides legacy guess)
          if (dh['list-type'] == 'region' && group == 'deployment')
            region_option = option;
        }
        if ('sample' in dh)
          option.sample = dh.sample;
        if ('choice' in dh)
          option.choice = dh.choice;
        if ('encrypted-protocols' in dh)
          option['encrypted-protocols'] = dh['encrypted-protocols'];
        if ('always-accept-certificates' in dh)
          option['always-accept-certificates'] = dh['always-accept-certificates'];
      } else if (['site_address', 'url'].indexOf(key) != -1) {
        group = "application";
        option['type'] = 'url';
      } else if (['domain', 'register-dns', 'web_server_protocol', 'path', 'ssl_certificate', 'ssl_private_key', 'ssl_intermediate_certificate'].indexOf(key) != -1) {
        group = "hidden";
      } else if (['username', 'password', 'prefix'].indexOf(key) != -1) {
        group = "application";
      } else if (option != region_option)
        group = "application";

      if (group !== undefined) {
        if (group in groups)
          groups[group].push(option);
        else
          groups[group] = [option];
      }

      var constraints = option.constraints || [];
      _.each(constraints, function(constraint) {
        // If protocols is in constraints, write out to the option so the form can read it
        if ('protocols' in constraint) {
          option.protocols = constraint.protocols;
          if (constraint.message === undefined)
            constraint.message = "supported protocols are: " + constraint.protocols;
        }
        if ('in' in constraint && (!('choice' in option)))
          option.choice = constraint['in'];
      });

    });

    _.each(options, function(option) {
      if (option.regex) {
        if (!_.isRegExp(option.regex)) {
          console.log("Regex '" + option.regex + "' is invalid for option " + option.id);
          delete option["regex"];
        }
      }
    });

    return {options: options, groups: groups, region_option: region_option};
  },

  getOptionsFromEnvironment: function(env) {
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
        else if (found.ref == tag_ref)
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
            callback(checkmate_yaml, remote);
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

/*
 * Authentication Service
 *
 * Handles authentication and impersonation
 *
 * identity stores:
 *   - the user's name
 *   - the user's token and auth source
 *   - if the user is an admin in Checkmate
 *
 * context stores:
 *   - the current tenant
 *   - the current user (tracks if we are impersonating or not)
 *
 * Examples:
 * - Racker who is a member of Checkmate Admins group:
 *   identity: Racker, Global Auth token, roles: *:admin
 *   context:  Racker username, role=admin
 *
 * When Cloud Auth account logged in:
 *   identity: cloud auth user, token, roles: admin on tenant
 *   context: tenant, cloud username
 *
 * Emits these broadcast events:
 * - logOn
 * - logOff
 * - contextChanged (always called: log on/off, impersonating/un-impersonating)
 *
**/
services.factory('auth', ['$resource', '$rootScope', function($resource, $rootScope) {
  var auth = {

    // Stores the user's identity and necessary credential info
    identity: {
      username: null,
      auth_url: null,
      token: null,
      expiration: null,
      endpoint_type: null, // Keystone | Rackspace Auth | Basic | Global Auth
      is_admin: false,
      loggedIn: false,
      user: null,
      tenants: null
    },
    // Stores the current context (when impersonating, it's a tenant user and
    // context when not, it's just a mirror of the current identity)
    context: {
      username: null,
      auth_url: null, // US, UK, etc...
      token: null, // token object with id, expires, and tenant info
      expiration: null,
      tenantId: null,
      catalog: {},
      impersonated: false,
      regions: null,
      user: null
    },
    endpoints: [],

    // Authenticate
    authenticate: function(endpoint, username, apikey, password, tenant, callback, error_callback) {
      var target = endpoint['uri'];
      var data;
      if (apikey) {
         data = JSON.stringify({
          "auth": {
            "RAX-KSKEY:apiKeyCredentials": {
              "username": username,
              "apiKey": apikey
            }
          }
        });
      } else if (password) {
        if (target == "https://identity-internal.api.rackspacecloud.com/v2.0/tokens") {
          data = JSON.stringify({
              "auth": {
                "RAX-AUTH:domain": {
                "name": "Rackspace"
                },
                "passwordCredentials": {
                  "username": username,
                  "password": password
                }
              }
            });
        } else {
          data = JSON.stringify({
            "auth": {
              "passwordCredentials": {
                "username": username,
                "password": password
              }
            }
          });
        }
      } else {
        return false;
      }

      if (target === undefined || target === null || target.length === 0) {
        headers = {};  // Not supported on server, but we should do it
      } else {
        headers = {"X-Auth-Source": target};
      }

      return $.ajax({
        type: "POST",
        contentType: "application/json; charset=utf-8",
        headers: headers,
        dataType: "json",
        url: is_chrome_extension ? target : "/authproxy",
        data: data
      }).success(function(response, textStatus, request) {
        //Populate identity
        auth.identity.username = response.access.user.name || response.access.user.id;
        auth.identity.user = response.access.user;
        auth.identity.auth_url = target;
        auth.identity.token = response.access.token;
        auth.identity.expiration = response.access.token.expires;
        auth.identity.endpoint_type = endpoint['scheme'];

        //Check if this user is an admin
        var is_admin = request.getResponseHeader('X-AuthZ-Admin') || 'False';
        auth.identity.is_admin = (is_admin === 'True');

        //Populate context
        auth.context.username = auth.identity.username;
        auth.context.user = response.access.user;
        auth.context.auth_url = target;
        auth.context.token = response.access.token;
        if (endpoint['scheme'] == "GlobalAuth") {
          auth.context.tenantId = null;
          auth.context.catalog = {};
          auth.context.impersonated = false;
        } else {
          if ('tenant' in response.access.token)
            auth.context.tenantId = response.access.token.tenant.id;
          else {
            auth.context.tenantId = null;
            headers['X-Auth-Token'] = auth.context.token.id;
            $.ajax({
              type: "GET",
              contentType: "application/json; charset=utf-8",
              headers: headers,
              dataType: "json",
              url: is_chrome_extension ? target : "/authproxy/v2.0/tenants"
            }).success(function(response, textStatus, request) {
              auth.identity.tenants = response.tenants;
              auth.save();
            });
          }
          auth.context.catalog = response.access.serviceCatalog;
          auth.context.impersonated = false;
        }

        //Parse region list
        var regions = _.union.apply(this, _.map(response.access.serviceCatalog, function(o) {return _.map(o.endpoints, function(e) {return e.region;});}));
        if ('RAX-AUTH:defaultRegion' in response.access.user && regions.indexOf(response.access.user['RAX-AUTH:defaultRegion']) == -1)
          regions.push(response.access.user['RAX-AUTH:defaultRegion']);
        auth.context.regions = _.compact(regions);

        //Save for future use
        auth.save();

        //Check token expiration
        auth.check_state();
        /*
        var expires = new Date(response.access.token.expires);
        var now = new Date();
        if (expires < now) {
          auth.expires = 'expired';
          $scope.auth.loggedIn = false;
        } else {
          $scope.auth.expires = expires - now;
          $scope.auth.loggedIn = true;
        }
        */

        callback(response);

        $rootScope.$broadcast('logIn');
        $rootScope.$broadcast('contextChanged');

      }).error(function(response) {
        error_callback(response);
      });
    },
    logOut: function() {
      auth.clear();
      localStorage.removeItem('auth');
      delete checkmate.config.header_defaults.headers.common['X-Auth-Token'];
      delete checkmate.config.header_defaults.headers.common['X-Auth-Source'];
      $rootScope.$broadcast('logOut');
    },
    impersonate: function(tenant, callback, error_callback) {
      var data;
      if (auth.identity.endpoint_type == 'GlobalAuth') {
        data = JSON.stringify({"RAX-AUTH:impersonation":
          {
            "user": {"username": tenant},
            "expire-in-seconds": 10800}
          });
        headers = {'X-Auth-Token': auth.identity.token.id,
                   'X-Auth-Source': "https://identity-internal.api.rackspacecloud.com/v2.0/RAX-AUTH/impersonation-tokens"};
      } else if (auth.identity.endpoint_type == 'Keystone') {
        data = JSON.stringify({
            "auth": {
              "token": {
                "id": auth.identity.token.id
              },
              'tenantId': tenant
            }
          });
        headers = {'X-Auth-Token': auth.identity.token.id,
                   'X-Auth-Source': auth.identity.auth_url};
      }
      return $.ajax({
        type: "POST",
        contentType: "application/json; charset=utf-8",
        headers: headers,
        dataType: "json",
        url: is_chrome_extension ? auth.auth_url : "/authproxy",
        data: data
      }).success(function(response) {
        auth.context.tenant = tenant;
        auth.context.token = response.access.token;

        if (auth.identity.endpoint_type == 'Keystone') {
          if ('tenant' in response.access.token)
            auth.context.tenantId = response.access.token.tenant.id;
          auth.context.catalog = response.access.serviceCatalog;
          auth.context.impersonated = false;
        }

        var regions = _.union.apply(this, _.map(response.access.serviceCatalog, function(o) {return _.map(o.endpoints, function(e) {return e.region;});}));
        if ('RAX-AUTH:defaultRegion' in response.access.user && regions.indexOf(response.access.user['RAX-AUTH:defaultRegion']) == -1)
          regions.push(response.access.user['RAX-AUTH:defaultRegion']);
        auth.context.regions = _.compact(regions);
        auth.save();

        callback(tenant, response);
      }).error(function(response) {
        error_callback(response);
      });
    },
    //Check all auth data and update state
    check_state: function() {
      if ('identity' in auth && auth.identity.expiration !== null) {
        var expires = new Date(auth.identity.expiration);
        var now = new Date();
        if (expires.getTime() > now.getTime()) {
          auth.identity.loggedIn = true;
          //Make all AJAX calls use context
          checkmate.config.header_defaults.headers.common['X-Auth-Token'] = auth.context.token.id;
          checkmate.config.header_defaults.headers.common['X-Auth-Source'] = auth.context.auth_url;
        } else {
          auth.clear();
        }
      } else
        auth.clear();
    },
    clear: function() {
      auth.identity = {};
      auth.context = {};
    },
    //Save to local storage
    save: function() {
      var data = {auth: {identity: auth.identity, context: auth.context, endpoints: auth.endpoints}};
      //Save for future use
      localStorage.setItem('auth', JSON.stringify(data));
    },
    //Restore from local storage
    restore: function() {
      var data = localStorage.getItem('auth');
      if (data !== undefined && data !== null)
        data = JSON.parse(data);
      if (data !== undefined && data !== null && data != {} && 'auth' in data && 'identity' in data.auth && 'context' in data.auth) {
        auth.identity = data.auth.identity;
        auth.context = data.auth.context;
        auth.endpoints = data.auth.endpoints;
        auth.check_state();
      }
    },
    parseWWWAuthenticateHeaders: function(headers) {
      headers = headers.split(',');
      var parsed = _.map(headers, function(entry) {
        entry = entry.trim();
        try {
          var scheme = entry.match(/^([\w\-]+)/)[0];
          var realm = entry.match(/realm=['"]([^'"]+)['"]/)[1];
          var uri = entry.match(/uri=['"]([^'"]+)['"]/)[1];
          return {scheme: scheme, realm: realm, uri: uri};
        } catch(err) {
          console.log("Error parsing WWW-Authenticate entry", entry);
          return {};
        }
      });
      auth.endpoints = _.compact(parsed);
    }
  };

  // Restore login from session
  auth.restore();

  return auth;
}]);
