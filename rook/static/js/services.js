var services = angular.module('checkmate.services', ['ngResource']);

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
          console.log("Invalid state '" + task.state + "'.");
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
          console.log("Invalid state '" + task.state + "'.");
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
    var options_to_display = [];
    var option_headers = {};
    var DEFAULT_OPTIONS = ['application', 'server', 'load-balancer', 'database', 'dns'];
    var DEFAULT_HEADERS = { 'application': 'Application Options', 'server': 'Server Options', 'load-balancer': 'Load Balancer Options', 'database': 'Database Options', 'dns': 'DNS Options'};


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

    if(blueprint['meta-data'] && blueprint['meta-data']['reach-info'] && blueprint['meta-data']['reach-info']['option-groups']) {
      _.each(blueprint['meta-data']['reach-info']['option-groups'], function(opt_group){
        if(typeof(opt_group) === "string"){
          options_to_display.push(opt_group);
          option_headers[opt_group] = opt_group + " Options";
        } else if(typeof(opt_group) === "object"){
          for (var key in opt_group) {
            if (opt_group.hasOwnProperty(key)) {
              options_to_display.push(key);
              option_headers[key] = opt_group[key];
            }
          }
        }
      });
    }
    else {
      options_to_display = DEFAULT_OPTIONS;
      option_headers = DEFAULT_HEADERS;
    }

    return { options: options, groups: groups, region_option: region_option, options_to_display: options_to_display, option_headers: option_headers };
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

/* Github APIs for blueprint parsing*/
services.factory('github', ['$http', function($http) {
  var me = {

    // Determine api call url based on whether the repo is on GitHub website or hosted Github Enterprise
    get_api_details: function(uri) {
      var api = {};
      var host_parts = uri.host().split(':');
      var domain = host_parts[0];
      var port = host_parts.length > 1 ? ':'+ host_parts[1] : '';

      if(/github\.com$/i.test(domain)) {
        // The repo is on the Github website
        api.server = uri.protocol() + '://' + 'api.github.com' + port;
        api.url = (checkmate_server_base || '') + '/githubproxy/';
        return api;
      }

      // The repo is on Github Enterprise
      api.server = uri.protocol() + '://' + uri.host();
      api.url = (checkmate_server_base || '') + '/githubproxy/api/v3/';
      return api;
    },

    //Parse URL and returns the github components (org, user, repo) back
    parse_org_url: function(url, callback) {
      var results = {};
      var u = URI(url);
      var parts = u.path().substring(1).split('/');
      var first_path_part = parts[0];
      results.server = u.protocol() + '://' + u.host(); //includes port
      results.url = u.href();
      results.api = this.get_api_details(u);
      results.owner = first_path_part;
      if (parts.length > 1) {
        results.repo = {name: parts[1]};
      } else {
        results.repo = {};
      }
      //Test if org
      $http({method: 'HEAD', url: results.api.url + 'orgs/' + first_path_part,
          headers: {'X-Target-Url': results.api.server, 'accept': 'application/json'}}).
      success(function(data, status, headers, config) {
        //This is an org
        results.org = first_path_part;
        results.user = null;
        if(callback) callback();
      }).
      error(function(data, status, headers, config) {
        //This is not an org (assume it is a user)
        results.org = null;
        results.user = first_path_part;
        if(callback) callback();
      });
      return results;
    },


    //Load all repos for owner
    get_repos: function(remote, callback, error_callback) {
      var path = remote.api.url;
      if (remote.org !== null) {
        path += 'orgs/' + remote.org + '/repos';
      } else
        path += 'users/' + remote.user + '/repos';
      console.log("Loading: " + path);
      $http({method: 'GET', url: path, headers: {'X-Target-Url': remote.api.server, 'accept': 'application/json'}}).
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
      var path = remote.api.url + 'repos/' + remote.owner + '/' + repo_name;
      console.log("Loading: " + path);
      $http({method: 'GET', url: path, headers: {'X-Target-Url': remote.api.server, 'accept': 'application/json'}}).
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
      $http({method: 'GET', url: remote.api.url + 'repos/' + remote.owner + '/' + remote.repo.name + '/git/refs',
          headers: {'X-Target-Url': remote.api.server, 'accept': 'application/json'}}).
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
      $http({method: 'GET', url: remote.api.url + 'repos/' + remote.owner + '/' + remote.repo.name + '/git/refs',
          headers: {'X-Target-Url': remote.api.server, 'accept': 'application/json'}}).
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
      var repo_url = remote.api.url + 'repos/' + remote.owner + '/' + remote.repo.name;
      $http({method: 'GET', url: repo_url + '/git/trees/' + remote.branch.commit,
          headers: {'X-Target-Url': remote.api.server, 'accept': 'application/json'}}).
      success(function(data, status, headers, config) {
        var checkmate_yaml_file = _.find(data.tree, function(file) {return file.path == "checkmate.yaml";});
        if (checkmate_yaml_file === undefined) {
          error_callback("No 'checkmate.yaml' found in the repository '" + remote.repo.name + "'");
        } else {
          $http({method: 'GET', url: repo_url + '/git/blobs/' + checkmate_yaml_file.sha,
              headers: {'X-Target-Url': remote.api.server, 'Accept': 'application/vnd.github.v3.raw'}}).
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
    },

    get_contents: function(remote, url, content_item, callback){
      var destination_path = URI(url).path();
      var path = '/githubproxy' + destination_path + "/contents/" + content_item;
      return $http({method: 'GET', url: path, headers: {'X-Target-Url': remote.api.server, 'accept': 'application/json'}}).
        success(function(data, status, headers, config) {
          callback(data);
        }).
        error(function() {
          console.log('Failed to retrieve ' + content_item + ' from ' + url);
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
services.factory('auth', ['$http', '$resource', '$rootScope', '$q', function($http, $resource, $rootScope, $q) {
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

    error_message: "",
    selected_endpoint: null,

    generate_auth_data: function(token, tenant, apikey, pin_rsa, username, password, scheme) {
      var data = {};
      if (token) {
        data = {
          "auth": {
            "token": { "id": token },
            "tenantId": tenant
            }
          };
      } else if (apikey) {
         data = {
          "auth": {
            "RAX-KSKEY:apiKeyCredentials": {
              "username": username,
              "apiKey": apikey
            }
          }
        };
      } else if (pin_rsa) {
        data = {
          "auth": {
            "RAX-AUTH:domain": {
              "name": "Rackspace"
            },
            "RAX-AUTH:rsaCredentials": {
              "username": username,
              "tokenKey": pin_rsa
            }
          }
        };
      } else if (password) {
        if (scheme == "GlobalAuth") {
          data = {
              "auth": {
                "RAX-AUTH:domain": {
                "name": "Rackspace"
                },
                "passwordCredentials": {
                  "username": username,
                  "password": password
                }
              }
            };
        } else {
          data = {
            "auth": {
              "passwordCredentials": {
                "username": username,
                "password": password
              }
            }
          };
        }
      } else {
        return false;
      }
      return JSON.stringify(data);
    },

    fetch_identity_tenants: function(endpoint, token) {
      var headers = {
        'X-Auth-Source': endpoint['uri'],
        'X-Auth-Token': token.id
      };
      $.ajax({
        type: "GET",
        contentType: "application/json; charset=utf-8",
        headers: headers,
        dataType: "json",
        url: is_chrome_extension ? endpoint['uri'] : "/authproxy/v2.0/tenants"
      }).success(function(response, textStatus, request) {
        auth.identity.tenants = response.tenants;
        auth.save();
      });
    },

    create_identity: function(response, params) {
      //Populate identity
      var identity = {};
      var endpoint = params.endpoint;
      var endpoint_parts = URI(endpoint.uri);
      var headers = params.headers;
      identity.username = response.access.user.name || response.access.user.id;
      identity.user = response.access.user;
      identity.token = response.access.token;
      identity.expiration = response.access.token.expires;
      identity.auth_host = endpoint_parts.protocol() + '://' + endpoint_parts.host();
      identity.auth_url = endpoint['uri'];
      identity.endpoint_type = endpoint['scheme'];

      // Admin information
      var is_admin = headers('X-AuthZ-Admin') || 'False';
      identity.is_admin = (is_admin === 'True');

      if (identity.is_admin)
        identity.tenants = JSON.parse( localStorage.previous_tenants || "[]" );

      return identity;
    },

    get_regions: function(response) {
      // TODO: un-minify this :P
      //Parse region list
      var regions = _.union.apply(this, _.map(response.access.serviceCatalog, function(o) {return _.map(o.endpoints, function(e) {return e.region;});}));
      if ('RAX-AUTH:defaultRegion' in response.access.user && regions.indexOf(response.access.user['RAX-AUTH:defaultRegion']) == -1)
        regions.push(response.access.user['RAX-AUTH:defaultRegion']);
      return _.compact(regions);
    },

    create_context: function(response, params) {
      //Populate context
      var context = {};
      context.username = response.access.user.name || response.access.user.id; // auth.identity.username;
      context.user = response.access.user;
      context.token = response.access.token;
      context.auth_url = params.endpoint['uri'];
      context.regions = auth.get_regions(response);

      if (params.endpoint['scheme'] == "GlobalAuth") {
        context.tenantId = null;
        context.catalog = {};
        context.impersonated = false;
      } else {
        if ('tenant' in response.access.token)
          context.tenantId = response.access.token.tenant.id;
        else {
          context.tenantId = null;
          auth.fetch_identity_tenants(params.endpoint, context.token);
        }
        context.catalog = response.access.serviceCatalog;
        context.impersonated = false;
      }

      return context;
    },

    // Authenticate
    authenticate: function(endpoint, username, apikey, password, token, pin_rsa, tenant, callback, error_callback) {
      var headers,
          target = endpoint['uri'],
          data = this.generate_auth_data(token, tenant, apikey, pin_rsa, username, password, endpoint.scheme);
      if (!data) return false;

      if (target === undefined || target === null || target.length === 0) {
        headers = {};  // Not supported on server, but we should do it
      } else {
        headers = {"X-Auth-Source": target};
      }
      auth.selected_endpoint = endpoint;

      var url = is_chrome_extension ? target : "/authproxy";
      var config = { headers: headers };
      return $http.post(url, data, config)
        .success(function(response, status, headers, config) {
          var params = { headers: headers, endpoint: endpoint };
          auth.context = auth.create_context(response, params);
          auth.identity = auth.create_identity(response, params);
          auth.identity.context = _.clone(auth.context);
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
        })
        .error(function(response, status, headers, config) {
          error_callback(response);
        });
    },

    logOut: function(broadcast) {
      if (broadcast === undefined) broadcast = true;
      auth.clear();
      localStorage.removeItem('auth');
      delete checkmate.config.header_defaults.headers.common['X-Auth-Token'];
      delete checkmate.config.header_defaults.headers.common['X-Auth-Source'];
      if (broadcast)
        $rootScope.$broadcast('logOut');
    },

    get_tenant_id: function(username, token) {
      var url = is_chrome_extension ? auth.context.auth_url : "/authproxy/v2.0/tenants";
      var config = { headers: { 'X-Auth-Token': token } };
      return $http.get(url, config)
        .then(
          // Success
          function(response) {
            var numbers = /^\d+$/;
            var tenant = _.find(response.data.tenants, function(tenant) { return tenant.id.match(numbers); });
            return tenant.id;
          },
          // Error
          function(response) {
            console.log("Error fetching tenant ID:\n" + response);
          });
    },

    re_authenticate: function(token, tenant) {
      var url = is_chrome_extension ? auth.context.auth_url : "/authproxy/v2.0/tokens";
      var data = this.generate_auth_data(token, tenant);
      return $http.post(url, data);
    },

    generate_impersonation_data: function(username, endpoint_type) {
      var data = {};
      if (endpoint_type == 'GlobalAuth') {
        data = {
          "RAX-AUTH:impersonation": {
            "user": {"username": username},
            "expire-in-seconds": 10800
          }
        };
      }
      /* For Private Clouds, in the future
      else if (endpoint_type == 'Keystone') {
        data = {
          "auth": {
            "token": { "id": auth.identity.token.id },
            'tenantId': username
          }
        };
      } */
      return JSON.stringify(data);
    },

    get_impersonation_url: function(endpoint_type) {
      var impersonation_url = "";
      switch(endpoint_type) {
        case 'GlobalAuth':
          impersonation_url = auth.identity.auth_host + "/v2.0/RAX-AUTH/impersonation-tokens";
          break;
        case 'Keystone':
          impersonation_url = auth.identity.auth_url;
          break;
      }
      return impersonation_url;
    },

    store_context: function(context) {
      if (!auth.identity.tenants)
        auth.identity.tenants = [];

      auth.identity.tenants = _.reject(auth.identity.tenants, function(tenant) {
        return tenant.username == context.username;
      });
      auth.identity.tenants.unshift(_.clone(context));
      if (auth.identity.tenants.length > 10)
        auth.identity.tenants.pop();
    },

    exit_impersonation: function() {
      auth.context = _.clone(auth.identity.context);
      auth.check_state();
      auth.save();
    },

    is_impersonating: function() {
      return auth.identity.username != auth.context.username;
    },

    impersonate_success: function(username, response, deferred) {
      this.get_tenant_id(username, response.data.access.token.id).then(
        // Success
        function(tenant_id) {
          auth.re_authenticate(response.data.access.token.id, tenant_id).then(
            // Success
            function(re_auth_response) {
              auth.context.username = username;
              auth.context.token = response.data.access.token;
              auth.context.auth_url = auth.identity.auth_url.replace('-internal', '');
              auth.context.tenantId = tenant_id;
              auth.context.catalog = re_auth_response.data.access.serviceCatalog;
              auth.context.regions = auth.get_regions(re_auth_response.data);
              auth.store_context(auth.context);
              auth.context.impersonated = true;
              auth.save();
              auth.check_state();
              deferred.resolve('Impersonation Successful!');
            },
            // Error
            function(catalog_response) {
              auth.impersonate_error(catalog_response, deferred);
            }
          );
        },
        // Error
        function(tenant_response) {
          auth.impersonate_error(tenant_response, deferred);
        }
      );
      return deferred;
    },

    impersonate_error: function(response, deferred) {
      console.log("Impersonation error: " + response);
      return deferred.reject(response);
    },

    impersonate: function(username) {
      var deferred = $q.defer();
      var url = is_chrome_extension ? auth.identity.auth_url : "/authproxy";
      var data = auth.generate_impersonation_data(username, auth.identity.endpoint_type);
      var headers = {
          'X-Auth-Token': auth.identity.token.id,
          'X-Auth-Source': auth.get_impersonation_url(auth.identity.endpoint_type)
      };
      var config = {headers: headers};
      $http.post(url, data, config).then(
        // Success
        function(response) {
          auth.impersonate_success(username, response, deferred);
        },
        // Error
        function(response) {
          auth.impersonate_error(response, deferred);
        });

      return deferred.promise;
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
      localStorage.setItem('auth', JSON.stringify(data));

      var previous_tenants = _.map(auth.identity.tenants, function(tenant) {
        return _.pick(tenant, 'username', 'tenantId'); // remove sensitive information
      });
      localStorage.setItem('previous_tenants', JSON.stringify(previous_tenants || "[]"));
    },

    //Restore from local storage
    restore: function() {
      var data = localStorage.getItem('auth');
      if (data !== undefined && data !== null)
        data = JSON.parse(data);
      if (data !== undefined && data !== null && data != {} && 'auth' in data && 'identity' in data.auth && 'context' in data.auth) {
        // Check if stored data is in older format
        if (data.auth.identity.auth_host === undefined) {
          auth.clear();
        } else {
          auth.identity = data.auth.identity;
          auth.context = data.auth.context;
          auth.endpoints = data.auth.endpoints;
          auth.check_state();
        }
      }
    },

    parseWWWAuthenticateHeaders: function(headers) {
      headers = headers.split(',');
      var parsed = _.map(headers, function(entry) {
        var endpoint = {};
        entry = entry.trim();
        try {
          var scheme = entry.match(/^([\w\-]+)/)[0];
          var realm = entry.match(/realm=['"]([^'"]+)['"]/)[1];
          var uri = entry.match(/uri=['"]([^'"]+)['"]/)[1];
          endpoint = { scheme: scheme, realm: realm, uri: uri };
        } catch(err) {
          console.log("Error parsing WWW-Authenticate entry", entry);
          return null;
        }

        try {
          var priority = entry.match(/priority=['"]([^'"]+)['"]/)[1];
          endpoint.priority = parseInt(priority, 10);
        } catch(err) {
          console.log('Error parsing priority from WWW-Authenticate entry', entry);
        }
        return endpoint;
      });

      auth.endpoints = _.compact(parsed).sort(function(a, b){
        if(typeof(a.priority) === 'number' && typeof(b.priority) === 'number') {
          return a.priority - b.priority;
        } else if(typeof(a.priority) === 'number') {
          return -1;
        } else if(typeof(b.priority) === 'number') {
          return 1;
        } else {
          var x = a.realm.toLowerCase(),
              y = b.realm.toLowerCase();
          return (x < y) ? (-1) : (x > y ? 1 : 0);
        }
      });
    }
  };

  // Restore login from session
  auth.restore();

  return auth;
}]);

services.factory('pagination', function(){
  function buildPagingParams(){
    var paging_params = [];

    paging_params.push('limit=' + this.limit);
    paging_params.push('offset=' + this.offset);

    return '?' + paging_params.join('&');
  }

  function _buildPagingLinks(current_page, total_pages, base_url, offset, limit){
    var counter = 0,
        links = { middle_numbered_links: [], separator: '...',
                  hide_first_separator: true, hide_last_separator: true },
        NUM_OF_LINKS_AT_ENDS = 3,
        NUM_OF_LINKS_IN_CENTER = 5,
        TOTAL_LINKS_TO_SHOW = (NUM_OF_LINKS_AT_ENDS * 2) + NUM_OF_LINKS_IN_CENTER;

    function _buildGroupedNumberedPageLinks(){
      var first_numbered_links = [],
          middle_numbered_links = [],
          last_numbered_links = [];

      _.each([current_page - 2, current_page - 1, current_page, current_page + 1, current_page + 2], function(num){
        if(num > 0 && num <= total_pages) {
          middle_numbered_links.push({ uri: base_url + '?limit=' + limit + '&offset=' + (num-1)*limit,
                                    text: num });
        }
      });

      for(var i=NUM_OF_LINKS_AT_ENDS; i>0; i--){
        if(!(_.find(middle_numbered_links, function(link){ return link.text == i; }))){
          first_numbered_links.unshift({ uri: base_url + '?limit=' + limit + '&offset=' + (i-1)*limit,
                                      text: i });
        }
      }

      for(var i=(total_pages - NUM_OF_LINKS_AT_ENDS); i < total_pages; i++){
        if(!(_.find(middle_numbered_links, function(link){ return link.text == i+1; }))){
        last_numbered_links.push({ uri: base_url + '?limit=' + limit + '&offset=' + (i)*limit,
                                    text: i+1 });
        }
      }

      links.first_numbered_links = first_numbered_links;
      links.middle_numbered_links = middle_numbered_links;
      links.last_numbered_links = last_numbered_links;

      links.hide_first_separator = (first_numbered_links.length === 0) || (_.first(middle_numbered_links).text - _.last(first_numbered_links).text) === 1;
      links.hide_last_separator = (last_numbered_links.length === 0) || (_.first(last_numbered_links).text - _.last(middle_numbered_links).text) === 1;
    }

    if(total_pages > 1) {
      if(total_pages > TOTAL_LINKS_TO_SHOW){
        _buildGroupedNumberedPageLinks();
      } else {
        while(counter < total_pages){
          links.middle_numbered_links.push({ uri: base_url + '?limit=' + limit + '&offset=' + (counter * limit),
                                      text: counter + 1 });
          counter++;
        }
      }

      links.next = { uri: base_url + '?limit=' + limit + '&offset=' + (offset + limit),
                     text: 'Next' };
      links.previous = { uri: base_url + '?limit=' + limit + '&offset=' + (offset - limit),
                         text: 'Previous' };

      if(current_page === 1) {
        links.disable_previous = true;
      }

      if(current_page === total_pages || total_pages === 0) {
        links.disable_next = true;
      }
    }

    return links;
  }

  function getPagingInformation(total_item_count, base_url){
    var current_page,
        total_pages,
        page_links;

    if(!this.offset || total_item_count === 0){
      current_page = 1;
    } else if(this.offset > 0 && this.offset < this.limit) {
      current_page = 2;
    } else {
      current_page = parseInt(this.offset/this.limit, 10) + 1;
    }

    total_pages = Math.ceil(total_item_count / this.limit);
    page_links = _buildPagingLinks(current_page, total_pages, base_url, this.offset, this.limit);

    return {
             currentPage: current_page,
             totalPages: total_pages,
             links: page_links
           };
  }

  function _getValidPageParams(offset, limit){
    var valid_offset,
        valid_limit,
        parsed_offset = parseInt(offset, 10),
        parsed_limit = parseInt(limit, 10),
        DEFAULT_PAGE_LIMIT = 20;

    if(parsed_limit && parsed_limit > 0) {
      valid_limit = parsed_limit;
    } else {
      valid_limit = DEFAULT_PAGE_LIMIT;
    }

    if(parsed_offset && parsed_offset > 0 && (parsed_offset % valid_limit) === 0) {
      valid_offset = parsed_offset;
    } else if(parsed_offset && parsed_offset > 0){
      valid_offset = parsed_offset - (parsed_offset % valid_limit);
    } else {
      valid_offset = 0;
    }

    return { offset: valid_offset, limit: valid_limit };
  }

  function buildPaginator(offset, limit){
    var valid_params = _getValidPageParams(offset, limit);

    return { offset: valid_params.offset,
             limit: valid_params.limit,
             buildPagingParams: buildPagingParams,
             getPagingInformation: getPagingInformation };
  }

  return { buildPaginator: buildPaginator };
});

services.factory('deploymentDataParser', function(){
  function formatData(data) {
    var formatted_data = {};

    try {
      var lb = _.find(data.resources, function(r, k) { return r.type == 'load-balancer';});
      if ('instance' in lb) {
        formatted_data.vip = lb.instance.public_ip;
      }
    }
    catch (error) {
      console.log(error);
    }

    var url;
    try {
      if (typeof data.inputs.blueprint.url == "string") {
        url = data.inputs.blueprint.url;
      } else {
        url = data.inputs.blueprint.url.url;
      }
      formatted_data.path = url;
      var u = URI(url);
      formatted_data.domain = u.hostname();
    }
    catch (error) {
      console.log("url not found", error);

      var domain = null;
      //Find domain in inputs
      try {
        domain = data.inputs.blueprint.domain;
        formatted_data.domain = domain;
      }
      catch (error) {
        console.log(error);
      }
      //If no domain, use load-balancer VIP
      if (domain === null) {
        domain = formatted_data.vip;
      }
      //Find path in inputs
      var path = "/";
      try {
        path = data.inputs.blueprint.path;
      }
      catch (error) {
        console.log(error);
      }
      if (domain !== undefined && path !== undefined)
        formatted_data.path = "http://" + domain + path;
    }
    try {
      var user = _.find(data.resources, function(r, k) { return r.type == 'user';});
      if (user !== undefined && 'instance' in user) {
        formatted_data.username = user.instance.name;
        formatted_data.password = user.instance.password;
      }
    }
    catch (error) {
      console.log(error);
    }

    try {
      var keypair = _.find(data.resources, function(r, k) { return r.type == 'key-pair';});
      if (keypair !== undefined && 'instance' in keypair) {
        formatted_data.private_key = keypair.instance.private_key;
      }
    }
    catch (error) {
      console.log(error);
    }

    formatted_data.resources = _.toArray(data.resources);
    formatted_data.master_server = _.find(formatted_data.resources, function(resource) {
        return (resource.component == 'linux_instance' && resource.service == 'master');
    });

    formatted_data.clippy = {};
    var server_data = [];
    var database_data = [];
    var lb_data = [];
    _.each(formatted_data.resources, function(resource) {
        if (resource.component == 'linux_instance') {
            server_data.push('  ' + resource.service + ' server: ' + resource['dns-name']);
            try {
              if (resource.instance.public_ip === undefined) {
                for (var nindex in resource.instance.interfaces.host.networks) {
                    var network = resource.instance.interfaces.host.networks[nindex];
                    if (network.name == 'public_net') {
                        for (var cindex in network.connections) {
                            var connection = network.connections[cindex];
                            if (connection.type == 'ipv4') {
                                resource.instance.public_ip = connection.value;
                                break;
                            }
                        }
                        break;
                    }
                }
              }
              server_data.push('    IP:      ' + resource.instance.public_ip);
            } catch (err) {}
            server_data.push('    Role:    ' + resource.service);
            server_data.push('    root pw: ' + resource.instance.password);
        }
        else if(resource.type == 'database') {
          database_data.push('  ' + resource.service + ' database: ' + resource['dns-name']);
          try {
            database_data.push('    Host:       ' + resource.instance.interfaces.mysql.host);
            database_data.push('    Username:   ' + (resource.instance.interfaces.mysql.username || formatted_data.username));
            database_data.push('    Password:   ' + (resource.instance.interfaces.mysql.password || formatted_data.password));
            database_data.push('    DB Name:    ' + resource.instance.interfaces.mysql.database_name);
          } catch(err) {
            // Do nothing - probably a MySQL on VMs build
          }
        }
        else if(resource.type == 'load-balancer') {
          lb_data.push('  ' + resource.service + ' load-balancer: ' + resource['dns-name']);
          lb_data.push('    Public VIP:       ' + resource.instance.public_ip);
        }
    });

    if (formatted_data.username === undefined) {
        _.each(formatted_data.resources, function(resource) {
            if (resource.type == 'application' && resource.instance !== undefined) {
                _.each(resource.instance, function(instance) {
                    if (instance.admin_user !== undefined) {
                        formatted_data.username = instance.admin_user;
                    }
                    if (instance.admin_password !== undefined) {
                        formatted_data.password = instance.admin_password;
                    }
                });
            }
        });
    }

    formatted_data.clippy.server_data = server_data.join('\n');
    formatted_data.clippy.database_data = database_data.join('\n');
    formatted_data.clippy.lb_data = lb_data.join('\n');

    return formatted_data;
  }
  return { formatData: formatData };
});

services.factory('config', function($location){
  function environment() {
    var ENVIRONMENTS = { 'localhost': 'local',
                          'api.dev.chkmate.rackspace.net': 'dev',
                          'staging.chkmate.rackspace.net': 'staging',
                          'api.qa.chkmate.rackspace.net': 'qa',
                          'preprod.chkmate.rackspace.net': 'preprod',
                          'checkmate.rackspace.net': 'production.net',
                          'checkmate.rackspace.com': 'production.com' };
    return ENVIRONMENTS[$location.host()];
  }
  return { environment: environment };
});

services.factory('webengage', function(config){
  var LICENSE_CODES = { local: '~99198c48',
                        'dev': '~c2ab32db',
                        'production.net': '~10a5cb78d',
                        'production.com': '~2024bc52' };
  function init(){
    var licenseCode = LICENSE_CODES[config.environment()];
    if(licenseCode){
      window.webengageWidgetInit = window.webengageWidgetInit || function(){
        webengage.init({
          licenseCode: licenseCode
        }).onReady(function(){
          webengage.render();
        });
      };
      (function(d){
        var _we = d.createElement("script");
        _we.type = "text/javascript";
        _we.async = true;
        _we.src = (d.location.protocol == "https:" ? "//ssl.widgets.webengage.com" : "//cdn.widgets.webengage.com") + "/js/widget/webengage-min-v-3.0.js";
        var _sNode = d.getElementById("webengage_script_tag");
        _sNode.parentNode.insertBefore(_we, _sNode);
      })(document);
    }
  }

  return { init: init };
});

