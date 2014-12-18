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

      $('.task').hover(function() {
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

    calculateStatistics: function(tasks){
      totalTime = 0;
      timeRemaining  = 0;
      taskStates = {
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
          totalTime += parseInt(task["internal_attributes"]["estimated_completed_in"], 10);
        } else {
          totalTime += 10;
        }
        switch(parseInt(task.state, 0)) {
          case -1:
            taskStates["error"] += 1;
            break;
          case 1:
            taskStates["future"] += 1;
            break;
          case 2:
            taskStates["likely"] += 1;
            break;
          case 4:
            taskStates["maybe"] += 1;
            break;
          case 8:
            if ('internal_attributes' in  task && 'task_state' in task.internal_attributes && task.internal_attributes.task_state.state == 'FAILURE')
                taskStates["error"] += 1;
            else
                taskStates["waiting"] += 1;
            break;
          case 16:
            taskStates["ready"] += 1;
            break;
          case 128:
            taskStates["triggered"] += 1;
            break;
          case 32:
            taskStates["cancelled"] += 1;
            break;
          case 64:
            taskStates["completed"] += 1;
            if ("internal_attributes" in task && "estimated_completed_in" in task["internal_attributes"]) {
              timeRemaining -= parseInt(task["internal_attributes"]["estimated_completed_in"], 10);
            } else {
              timeRemaining -= 10;
            }
            break;
          default:
            console.log("Invalid state '" + task.state + "'.");
        }
      });
      timeRemaining += totalTime;

      return { totalTime: totalTime,
               timeRemaining: timeRemaining,
               taskStates: taskStates
             };
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
    receive: function(list, transform) {
      console.log("Receiving");

      var all_items = [],
          data = {};

      if (transform === null || transform === undefined)
          transform = function(item) {return item;};
      for (var attrname in list) {
        data[attrname] = list[attrname];
      }
      angular.forEach(list, function(value, key) {
        all_items.push(transform(value, key));
      });
      console.log('Done receiving ' + all_items.length + ' entries');
      return { count: all_items.length,
               all:   all_items,
               data:  data };
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
    var DEFAULT_HEADERS = { 'application': 'Application Options', 'server': 'Server Options', 'load-balancer': 'Load Balancer Options', 'database': 'Database Options', 'dns': 'DNS Options'};
    var DEFAULT_OPTIONS = _.keys(DEFAULT_HEADERS);

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
        } else {
          group = 'application';
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
services.factory('github', ['$http', '$q', '$cookies', '$cookieStore', function($http, $q, $cookies, $cookieStore) {
  var set_remote_owner_type = function(remote, type) {
    remote[type] = remote.owner;
    return remote;
  };


  var scope = {};

  scope.config = {
    url: 'https://github.com',
    isEnterprise: false,
    apiUrl: 'https://api.github.com',
    accessToken: $cookies.github_access_token
  };

  scope.currentUser = {};

  var get_config = function(url, content_type) {
    var config = {
      headers: {
        'X-Target-Url': url,
        'Accept': content_type || 'application/json'
      }
    };

    if (scope.config.accessToken) {
      config.headers.Authorization = 'token ' + scope.config.accessToken;
    }

    return config;
  };

  scope.set_user = function() {
    if (scope.config.accessToken) {
      var request = {
        method: 'GET',
        url: (checkmate_server_base || '') + '/githubproxy/user',
        headers: {
          'X-Target-Url': scope.config.apiUrl,
          'accept': 'application/json',
          'Authorization': 'token ' + scope.config.accessToken
        }
      };
      $http(request).
        success(function(data, status, headers, config) {
          scope.currentUser = data;
        }).
        error(function(data, status, headers, config) {
          console.log(data);
          scope.currentUser = {};
        });
    }
  };

  scope.logout = function() {
    scope.config = {};
    scope.currentUser = {};
    $cookieStore.remove('github_access_token');
  };

  scope.get_proxy_url = function(repo_url) {
      var uri = URI(repo_url);
      return '/githubproxy' + uri.path();
  };

  // Determine api call url based on whether the repo is on GitHub website or hosted Github Enterprise
  scope.get_api_details = function(uri) {
    var api = {};
    var host_parts = uri.host().split(':');
    var domain = host_parts[0];
    var port = host_parts.length > 1 ? ':'+ host_parts[1] : '';

    api.server = uri.protocol() + '://';
    api.url = (checkmate_server_base || '') + '/githubproxy/';

    if(/github\.com$/i.test(domain)) {
      // The repo is on the Github website
      api.server += 'api.github.com' + port;
      api.isEnterprise = false;
    } else {
      // The repo is on Github Enterprise
      api.server += uri.host();
      api.url += 'api/v3/';
      api.isEnterprise = true;
    }

    return api;
  };

  scope.set_github_url = function(uri) {
    var api = scope.get_api_details(uri);
    scope.config.url = url.protocol() + '://' + url.host();
    scope.config.apiUrl = url.protocol() + '://' + api.server + '/' + api.url;
    scope.config.isEnterprise = api.isEnterprise;
    scope.set_user();
  };

  scope.parse_url = function(url_string) {
    var remote = {};

    var url = URI(url_string);
    var hash = url.hash();
    var segments = url.path().substring(1).split('/');
    var first_path_part = segments[0];
    remote.server = url.protocol() + '://' + url.host(); //includes port
    remote.url = url.href();
    remote.api = scope.get_api_details(url);
    remote.owner = first_path_part;
    remote.repo = {};
    if (segments.length > 1) {
      remote.repo.name = segments[1];
    }
    remote.branch_name = hash;

    // Unknown at this point
    remote.org = null;
    remote.user = null;

    return remote;
  };

  //Parse URL and returns a promise back with the github components (org, user, repo)
  scope.parse_org_url = function(url) {
    var remote = scope.parse_url(url);
    var api_url = remote.api.url + 'orgs/' + remote.owner;
    var config = get_config(remote.api.server);

    return $http.head(api_url, config).
      then(
        function(response) { // If orgs call is successful
          return set_remote_owner_type(remote, 'org');
        },
        function(response) { // Assume it's a user otherwise
          return set_remote_owner_type(remote, 'user');
        }
      );
  };

  //Load all repos for owner
  scope.get_repos = function(remote) {
    var path = remote.api.url,
        GITHUB_MAX_PER_PAGE = 100;
    if (remote.org !== null) {
      path += 'orgs/' + remote.org + '/repos';
    } else
      path += 'users/' + remote.user + '/repos';
    console.log("Loading: " + path);
    var config = get_config(remote.api.server);
    config.params = { per_page: GITHUB_MAX_PER_PAGE };
    return $http.get(path, config).then(
      function(response) {
        return response.data;
      },
      function(response) {
        return $q.reject(response);
      }
    );
  };

  //Load one repo
  scope.get_repo = function(remote, repo_name, callback, error_callback) {
    var path = remote.api.url + 'repos/' + remote.owner + '/' + repo_name;
    console.log("Loading: " + path);
    $http.get(path, get_config(remote.api.server)).
      success(function(data, status, headers, config) {
        callback(data);
      }).
      error(function(data, status, headers, config) {
        var response = {data: data, status: status};
        error_callback(response);
      });
  };

  //Get all branches (and tags) for a repo
  scope.get_branches = function(remote, callback, error_callback) {
    var url = remote.api.url + 'repos/' + remote.owner + '/' + remote.repo.name + '/git/refs';
    $http.get(url, get_config(remote.api.server)).
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
  };

  // Get a single branch or tag and return it as an object (with type, name, and commit)
  scope.get_branch_from_name = function(remote, branch_name) {
    var url = remote.api.url + 'repos/' + remote.owner + '/' + remote.repo.name + '/git/refs';
    var config = get_config(remote.api.server);
    return $http.get(url, config)
      .then(
        // Success
        function(response) {
          var refs = response.data;
          var ref = {};

          //Only branches and tags
          var branch_ref = 'refs/heads/' + branch_name;
          var tag_ref = 'refs/tags/' + branch_name;
          var found = _.find(refs, function(item) {
            return item.ref == branch_ref || item.ref == tag_ref;
          });

          // No Branch or Ref Found: Reject!
          if (found === undefined) {
            var not_found_response = {data: "Branch or tag " + branch_name + " not found", status: "404"};
            return $q.reject(not_found_response);
          }

          //Format and return the data (we need name, type, and sha only)
          ref.commit = found.object.sha;
          if (found.ref == branch_ref) {
            ref.type = 'branch';
            ref.name = found.ref.substring(11);
          } else {
            ref.type = 'tag';
            ref.name = found.ref.substring(10);
          }

          return ref;
        },
        // Error
        function(response) {
          return $q.reject(response);
        }
      );
  };

  var _get_branch_name = function(remote) {
    return ((remote.branch && remote.branch.name) || remote.branch_name || 'master');
  };

  var _parse_blueprint = function(yaml_string, remote, username) {
    var checkmate_yaml;
    var branch_name = _get_branch_name(remote);
    var sanitized_yaml = yaml_string
                           .replace('%repo_url%', remote.url)
                           .replace('%username%', username || '%username%');
    checkmate_yaml = jsyaml.safeLoad(sanitized_yaml);
    return checkmate_yaml;
  };

  scope.get_blueprint = function(remote, username) {
    return scope.get_contents(remote, null, 'checkmate.yaml').then(
      function success(yaml_string) {
        try {
          return _parse_blueprint(yaml_string, remote, username);
        } catch(err) {
          var parse_error_response = {
            data: err.message,
            status: 400
          };
          return $q.reject(parse_error_response);
        }
      },
      // Error
      $q.reject
    );
  };

  scope.get_contents = function(remote, url, content_item){
    var path;
    if (url) {
      var destination_path = URI(url).path();
      path = '/githubproxy' + destination_path + "/contents/" + content_item;
    } else {
      var branch_name = _get_branch_name(remote);
      path = remote.api.url + 'repos/' + remote.owner + '/' + remote.repo.name + '/contents/' + content_item + "?ref=" + branch_name;
    }
    var config = get_config(remote.api.server, 'application/vnd.github.v3.raw');
    return $http.get(path, config).then(
      function(response) {
        return response.data;
      },
      function(response) {
        console.log('Failed to retrieve ' + content_item + ' from ' + url);
        return response;
      }
    );
  };

  scope.get_refs = function(repos, type) {
    var tags = [];
    var promises = [];

    if (!type) type = "";
    else type = '/' + type;
    if (!(repos instanceof Array)) {
      repos = [repos];
    }

    for (var i=0 ; i<repos.length ; i++) {
      var repo = repos[i];
      var refs_url = repo.git_refs_url.replace('{/sha}', type);
      var url = scope.get_proxy_url(refs_url);
      var config = get_config(refs_url);
      var promise = $http.get(url, config).then(
        function(response) { // Success
          tags.push(response.data);
        },
        function(response) { // Error
          tags.push([]);
        }
      );
      promises.push(promise);
    }

    return $q.all(promises).then(function() {
      if (tags.length == 1)
        tags = tags.pop();

      return tags;
    });
  };

  scope.get_tags = function(repos) {
    return scope.get_refs(repos, 'tags');
  };

  scope.set_user();

  return scope;
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
services.factory('auth', ['$http', '$resource', '$rootScope', '$q', '$cookieStore', function($http, $resource, $rootScope, $q, $cookieStore) {
  var auth = {};

  // Stores the user's identity and necessary credential info
  auth.identity = {
    username: null,
    auth_url: null,
    token: null,
    expiration: null,
    endpoint_type: null, // Keystone | Rackspace Auth | Basic | GlobalAuth
    is_admin: false,
    loggedIn: false,
    user: null,
    tenants: null
  };

  // Stores the current context (when impersonating, it's a tenant user and
  // context when not, it's just a mirror of the current identity)
  auth.context = {
    username: null,
    auth_url: null, // US, UK, etc...
    token: null, // token object with id, expires, and tenant info
    expiration: null,
    tenantId: null,
    catalog: {},
    impersonated: false,
    regions: null,
    user: null
  };
  auth.endpoints = [];

  auth.error_message = "";
  auth.selected_endpoint = null;

  auth.is_admin = function(strict) {
    var is_admin = auth.identity.is_admin;
    if (strict) {
      is_admin = is_admin && !auth.is_impersonating();
    }
    return is_admin;
  }

  auth.is_logged_in = function() {
    return auth.identity.loggedIn;
  }

  auth.is_current_tenant = function(tenant_id) {
    return auth.context.tenantId === tenant_id;
  }

  auth.get_tenants = function() {
    return _.values(auth.identity.tenants);
  }

  auth.switch_tenant = function(tenant_id) {
    var new_context = auth.identity.tenants[tenant_id];
    if (new_context) {
      auth.context = angular.copy(new_context);
    }
  }

  auth.generate_auth_data = function(token, tenant_name, apikey, pin_rsa, username, password, scheme) {
    var data = {};
    if (token) {
      data = {
        auth: {
          token: { id: token },
          tenantName: tenant_name
          }
        };
    } else if (apikey) {
       data = {
        auth: {
          "RAX-KSKEY:apiKeyCredentials": {
            username: username,
            apiKey: apikey
          }
        }
      };
    } else if (pin_rsa) {
      data = {
        auth: {
          "RAX-AUTH:domain": {
            name: "Rackspace"
          },
          "RAX-AUTH:rsaCredentials": {
            username: username,
            tokenKey: pin_rsa
          }
        }
      };
    } else if (password) {
      if (scheme == "GlobalAuth") {
        data = {
            auth: {
              "RAX-AUTH:domain": {
              name: "Rackspace"
              },
              passwordCredentials: {
                username: username,
                password: password
              }
            }
          };
      } else {
        data = {
          auth: {
            passwordCredentials: {
              username: username,
              password: password
            }
          }
        };
      }
    } else {
      return false;
    }
    return data;
  }

  auth.fetch_identity_tenants = function(endpoint, token) {
    var url = is_chrome_extension ? endpoint['uri'] : "/authproxy/v2.0/tenants";
    var config = {
      headers: {
        'X-Auth-Source': endpoint['uri'],
        'X-Auth-Token': token.id
      }
    };
    return $http.get(url, config).then(function(response) {
      return response.data.tenants;
    });
  }

  auth.create_identity = function(response, params) {
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

    return identity;
  }

  auth.get_regions = function(response) {
    // TODO: un-minify this :P
    //Parse region list
    var regions = _.union.apply(this, _.map(response.access.serviceCatalog, function(o) {return _.map(o.endpoints, function(e) {return e.region;});}));
    if ('RAX-AUTH:defaultRegion' in response.access.user && regions.indexOf(response.access.user['RAX-AUTH:defaultRegion']) == -1)
      regions.push(response.access.user['RAX-AUTH:defaultRegion']);
    return _.compact(regions);
  }

  auth.create_context = function(response, params) {
    var context = {};
    context.username = response.access.user.name || response.access.user.id; // auth.identity.username;
    context.user = response.access.user;
    context.token = response.access.token;
    context.auth_url = params.endpoint['uri'];
    context.regions = auth.get_regions(response);
    context.tenantId = null;
    context.catalog = {};
    context.impersonated = false;

    var is_admin = params.headers('X-AuthZ-Admin') === 'True';

    if (!is_admin) {
      if ('tenant' in response.access.token)
        context.tenantId = response.access.token.tenant.name;
      context.catalog = response.access.serviceCatalog;
    }

    return context;
  }

  var _get_tenant_token = function(tenant, config) {
    config.data.auth.tenantName = tenant.name;
    return $http(config).then(function(response) {
      var params = { endpoint: auth.selected_endpoint };
      return auth.create_context(response.data, params);
    });
  }

  var _authenticate_success = function(response) {
    var endpoint = auth.selected_endpoint;
    var params = { headers: response.headers, endpoint: endpoint };
    auth.context = auth.create_context(response.data, params);
    auth.identity = auth.create_identity(response.data, params);
    auth.identity.context = angular.copy(auth.context);

    if (auth.context.tenantId === null && !auth.is_admin()) {
      auth.fetch_identity_tenants(endpoint, auth.context.token)
        .then(function(tenants) {
          auth.identity.tenants = {};
          var promises = [];
          angular.forEach(tenants, function(tenant) {
            var deferred = $q.defer();
            promises.push(deferred.promise);
            _get_tenant_token(tenant, response.config).then(function(context) {
              var id = context.tenantId;
              auth.identity.tenants[id] = context;
              deferred.resolve(context);
            });
          });
          $q.all(promises).then(auth.save);
        });
    }

    if (auth.is_admin())
      auth.cache.tenants = JSON.parse( localStorage.previous_tenants || "[]" );

    auth.save();
    auth.check_state();

    $rootScope.$broadcast('logIn');
    $rootScope.$broadcast('contextChanged');
    return response;
  }

  var _authenticate_error = function(response) {
    console.log("Authentication Error:");
    console.log(response.data);
    response.message = 'Your credentials could not be verified';
    return $q.reject(response);
  }

  auth.authenticate = function(endpoint, username, apikey, password, token, pin_rsa, tenant_name) {
    var headers = {},
        target = endpoint['uri'],
        data = auth.generate_auth_data(token, tenant_name, apikey, pin_rsa, username, password, endpoint.scheme);
    if (!data) return $q.reject({ status: 401, message: 'No auth data was supplied' });
    auth.selected_endpoint = endpoint;

    if (target && target !== "") {
      headers["X-Auth-Source"] = target;
    }

    var url = is_chrome_extension ? target : "/authproxy";
    var config = { headers: headers };
    return $http.post(url, data, config)
      .then(_authenticate_success, _authenticate_error);
  }

  auth.logOut = function(broadcast) {
    if (broadcast === undefined) broadcast = true;
    auth.clear();
    localStorage.removeItem('auth');
    delete checkmate.config.header_defaults.headers.common['X-Auth-Token'];
    delete checkmate.config.header_defaults.headers.common['X-Auth-Source'];
    $cookieStore.remove('github_access_token');
    if (broadcast)
      $rootScope.$broadcast('logOut');
  }

  auth.get_tenant_id = function(username, token) {
    var url = is_chrome_extension ? auth.context.auth_url : "/authproxy/v2.0/tenants";
    var config = { headers: { 'X-Auth-Token': token } };
    return $http.get(url, config)
      .then(
        // Success
        function(response) {
          var mosso_name = /^MossoCloudFS/;
          var tenant = _.find(response.data.tenants, function(tenant) { return !tenant.name.match(mosso_name) });
          return tenant.name;
        },
        // Error
        function(response) {
          console.log("Error fetching tenant ID:\n" + response);
          return $q.reject(response);
        });
  }

  auth.re_authenticate = function(token, tenant_name) {
    var url = is_chrome_extension ? auth.context.auth_url : "/authproxy/v2.0/tokens";
    var data = auth.generate_auth_data(token, tenant_name);
    return $http.post(url, data);
  }

  auth.generate_impersonation_data = function(username, endpoint_type) {
    var data = {};
    if (auth.is_admin()) {
      data = {
        "RAX-AUTH:impersonation": {
          user: {username: username},
          "expire-in-seconds": 10800
        }
      };
    }
    /* For Private Clouds, in the future
    else if (endpoint_type == 'Keystone') {
      data = {
        auth: {
          token: { id: auth.identity.token.id },
          'tenantId': username
        }
      };
    } */
    return JSON.stringify(data);
  }

  auth.get_impersonation_url = function(endpoint_type) {
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
  }

  auth.cache = {};

  auth.cache_tenant = function(context) {
    if (!auth.cache.tenants)
      auth.cache.tenants = [];

    auth.cache.tenants = _.reject(auth.cache.tenants, function(tenant) {
      return tenant.username == context.username;
    });

    auth.cache.tenants.unshift(angular.copy(context));
    if (auth.cache.tenants.length > 10)
      auth.cache.tenants.pop();
  }

  auth.get_cached_tenant = function(username_or_tenant_id) {
    if (!username_or_tenant_id) return false;
    if (!auth.cache.tenants) return false;

    var info = username_or_tenant_id;
    for (idx in auth.cache.tenants) {
      var context = auth.cache.tenants[idx];
      if (context.username === info || context.tenantId === info) {
        return context;
      }
    }

    return false;
  }

  auth.is_valid = function(context) {
    if (!context) return false;
    if (!context.token) return false;

    var now = new Date();
    var context_expiration = new Date(context.token.expires || null);

    return context_expiration > now;
  }

  var _trim_cache_size = function(cache_name, size) {
    var cache_keys = cache_name + '_keys';
    var cache_size = Object.keys(auth.cache.contexts).length;
    if (!size || typeof size != 'number')
      size = 500;

    while (cache_size > size) {
      var key = auth.cache[cache_keys].shift();
      delete auth.cache[cache_name][key];
      cache_size--;
    }
  }

  auth.cache_context = function(context) {
    if (!context) return;

    if (!auth.cache.contexts)
      auth.cache.contexts = {};
    if (!auth.cache.contexts_keys)
      auth.cache.contexts_keys = [];

    var cached_context = angular.copy(context);
    if (context.username) {
      auth.cache.contexts[context.username] = cached_context;
      auth.cache.contexts_keys.push(context.username);
    }
    if (context.tenantId) {
      auth.cache.contexts[context.tenantId] = cached_context;
      auth.cache.contexts_keys.push(context.tenantId);
    }

    _trim_cache_size('contexts');

    return context;
  }

  auth.get_cached_context = function(username_or_tenant_id) {
    if (!auth.cache.contexts) return;
    return angular.copy(auth.cache.contexts[username_or_tenant_id]);
  }

  auth.exit_impersonation = function() {
    auth.context = angular.copy(auth.identity.context);
    auth.check_state();
    auth.save();
  }

  auth.is_impersonating = function() {
    return auth.identity.username != auth.context.username;
  }

  auth.impersonate_success = function(username, response, deferred, temporarily) {
    auth.get_tenant_id(username, response.data.access.token.id).then(
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
            auth.context.impersonated = true;
            auth.cache_context(auth.context);
            if (!temporarily) {
              auth.cache_tenant(auth.context);
            }
            auth.save();
            auth.check_state();
            deferred.resolve('Impersonation Successful!');
          },
          // Error
          function(catalog_response) {
            return auth.impersonate_error(catalog_response, deferred);
          }
        );
      },
      // Error
      function(tenant_response) {
        return auth.impersonate_error(tenant_response, deferred);
      }
    );
    return deferred;
  }

  auth.impersonate_error = function(response, deferred) {
    console.log("Impersonation error: " + response);
    return deferred.reject(response);
  }

  auth.impersonate = function(username, temporarily) {
    var deferred = $q.defer();
    var previous_context = auth.get_cached_context(username);
    if (previous_context && auth.is_valid(previous_context)) {
      auth.context = previous_context;
      if (!temporarily) {
        auth.cache_tenant(auth.context);
      }
      auth.check_state();
      deferred.resolve("Impersonation Successful! (cached)");
      return deferred.promise;
    }

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
        return auth.impersonate_success(username, response, deferred, temporarily);
      },
      // Error
      function(response) {
        return auth.impersonate_error(response, deferred);
      });

    return deferred.promise;
  }

  //Check all auth data and update state
  auth.check_state = function() {
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
  }

  auth.clear = function() {
    auth.identity = {};
    auth.context = {};
    auth.cache = {};
  }

  //Save to local storage
  auth.save = function() {
    var data = {auth: {identity: auth.identity, context: auth.context, endpoints: auth.endpoints, cache: auth.cache}};
    localStorage.setItem('auth', JSON.stringify(data));

    var previous_tenants = _.map(auth.cache.tenants, function(tenant) {
      return _.pick(tenant, 'username', 'tenantId'); // remove sensitive information
    });
    localStorage.setItem('previous_tenants', JSON.stringify(previous_tenants || "[]"));
  }

  //Restore from local storage
  auth.restore = function() {
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
        auth.cache = data.auth.cache || {};
        auth.cache.tenants = JSON.parse( localStorage.previous_tenants || "[]" );
        auth.check_state();
      }
    }
  }

  auth.parseWWWAuthenticateHeaders = function(headers) {
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

  // Restore login from session
  auth.restore();

  return auth;
}]);

services.factory('pagination', function(){
  function _buildPagingLinks(current_page, total_pages, original_url, offset, limit){
    var counter = 0,
        links = { middle_numbered_links: [], separator: '...',
                  hide_first_separator: true, hide_last_separator: true },
        NUM_OF_LINKS_AT_ENDS = 3,
        NUM_OF_LINKS_IN_CENTER = 5,
        TOTAL_LINKS_TO_SHOW = (NUM_OF_LINKS_AT_ENDS * 2) + NUM_OF_LINKS_IN_CENTER,
        uri = URI(original_url);

        uri.setSearch('limit', limit);

    function _buildGroupedNumberedPageLinks(){
      var first_numbered_links = [],
          middle_numbered_links = [],
          last_numbered_links = [];

      _.each([current_page - 2, current_page - 1, current_page, current_page + 1, current_page + 2], function(num){
        if(num > 0 && num <= total_pages) {
          uri.setSearch('offset', (num-1)*limit)
          middle_numbered_links.push({ uri: uri.href(), text: num });
        }
      });

      for(var i=NUM_OF_LINKS_AT_ENDS; i>0; i--){
        if(!(_.find(middle_numbered_links, function(link){ return link.text == i; }))){
          uri.setSearch('offset', (i-1)*limit)
          first_numbered_links.unshift({ uri: uri.href(), text: i });
        }
      }

      for(var i=(total_pages - NUM_OF_LINKS_AT_ENDS); i < total_pages; i++){
        if(!(_.find(middle_numbered_links, function(link){ return link.text == i+1; }))){
          uri.setSearch('offset', (i)*limit)
          last_numbered_links.push({ uri: uri.href(), text: i+1 });
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
          uri.setSearch('offset', counter*limit)
          links.middle_numbered_links.push({ uri: uri.href(), text: counter + 1 });
          counter++;
        }
      }

      uri.setSearch('offset', offset + limit)
      links.next = { uri: uri.href(), text: 'Next' };

      uri.setSearch('offset', offset - limit)
      links.previous = { uri: uri.href(), text: 'Previous' };

      if(current_page === 1) {
        links.disable_previous = true;
      }

      if(current_page === total_pages || total_pages === 0) {
        links.disable_next = true;
      }
    }

    return links;
  }

  function getPagingInformation(total_item_count, original_url){
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
    page_links = _buildPagingLinks(current_page, total_pages, original_url, this.offset, this.limit);

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
        DEFAULT_PAGE_LIMIT = 20,
        MAX_LIMIT = 100;

    // Limit
    if(parsed_limit && parsed_limit > 0) {
      valid_limit = parsed_limit;
    } else {
      valid_limit = DEFAULT_PAGE_LIMIT;
    }
    if (valid_limit > MAX_LIMIT) valid_limit = MAX_LIMIT;

    // Offset
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
    var changed_params = function() {
      return (offset && offset != valid_params.offset) || (limit && limit != valid_params.limit);
    };

    return { changed_params: changed_params,
             offset: valid_params.offset,
             limit: valid_params.limit,
             getPagingInformation: getPagingInformation };
  }

  return { buildPaginator: buildPaginator };
});

services.factory('deploymentDataParser', function(){
  var _get_vip = function(resources) {
    var vip;

    var lb = _.find(resources, function(resource) { return resource.type == 'load-balancer'; });
    if (lb && 'instance' in lb) {
      vip = lb.instance.public_ip;
    }

    return vip;
  }

  var _get_url_info = function(inputs, default_domain) {
    var url_info = {};
    var url;
    var domain;
    var blueprint;
    if (inputs)
      blueprint = inputs.blueprint;

    if (blueprint) {
      if (blueprint.url) {
        var blueprint_url = inputs.blueprint.url;
        if (typeof blueprint_url !== 'string') {
          blueprint_url = blueprint_url.url;
        }
        var uri = URI(blueprint_url);
        domain = uri.hostname();
        url = blueprint_url;
      } else {
        domain = blueprint.domain;
        url = 'http://' + domain + blueprint.path;
      }
    } else {
      domain = default_domain;
      url = 'http://' + domain + '/';
    }

    url_info.path = url;
    url_info.domain = domain;

    return url_info;
  }

  function formatData(data) {
    var formatted_data = {};

    var vip = _get_vip(data.resources);
    if (vip)
      formatted_data.vip = vip;

    var url_info = _get_url_info(data.inputs, formatted_data.vip);
    formatted_data.path = url_info.path;
    formatted_data.domain = url_info.domain;

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

angular.module('checkmate.services').factory('cmTenant', ['$resource', 'auth', function($resource, auth) {
  var scope = {};

  var params = { id: '@id' };
  var actions = { save: { method: 'PUT', params: params } };
  var Tenant = $resource('/admin/tenants/:id', params, actions);

  var add_tag_error = function(response) {
    console.log('cmTenant: Error adding tag');
    var tenant = response.config.data;
    tenant.tags = _.without(tenant.tags, tenant.new_tag);
    delete tenant.new_tag;
  };

  scope.add_tag = function(tenant, new_tag) {
    if (new_tag) {
      var current_tags = tenant.tags || [];
      var new_tags = current_tags.concat(new_tag);
      tenant.tags = _.uniq(new_tags);
      tenant.new_tag = new_tag;
      tenant.$save(null, null, add_tag_error);
    }
  };

  var remove_tag_error = function(response) {
    console.log('cmTenant: Error removing tag');
    var tenant = response.config.data;
    var tags = tenant.tags.concat(tenant.old_tag);
    tenant.tags = _.uniq(tags);
    delete tenant.old_tag;
  };

  scope.remove_tag = function(tenant, old_tag) {
    if (old_tag) {
      tenant.old_tag = old_tag;
      tenant.tags = _.without(tenant.tags, tenant.old_tag);
      tenant.$save(null, null, remove_tag_error);
    }
  };

  var clear_tags_error = function(response) {
    console.log('cmTenant: Error clearing tags');
    var tenant = response.config.data;
    tenant.tags = tenant.old_tags;
    delete tenant.old_tags;
  };

  scope.clear_tags = function() {
    tenant.old_tags = tenant.tags;
    tenant.tags = [];
    tenant.$save(null, null, clear_tag_error);
  };

  scope.get = function(id, callback, failure) {
    if (!auth.is_admin() || auth.is_impersonating()) {
      if (failure) failure();
      return {};
    }

    return Tenant.get({id: id}, callback, failure);
  };

  return scope;
}]);

services.factory('urlBuilder', function(){

  var scope = {};

  scope.cloudControlURL = function(resource_type, resource_id, region, tenant_id){
    if (!resource_id)
      return null;

    var host,
        path,
        RESOURCE_PATHS = {
          'server': '/next_gen_servers/',
          'legacy_server': '/first_gen_servers/',
          'load_balancer': '/load_balancers/',
          'database': '/dbaas/instances/'
        };

    if (region === 'LON') {
      host = "https://lon.cloudcontrol.rackspacecloud.com";
    } else {
      host = "https://us.cloudcontrol.rackspacecloud.com";
    }

    path = '/customer/' + tenant_id + RESOURCE_PATHS[resource_type] + region + '/' + resource_id;

    return host + path;
  }

  scope.myCloudURL = function(resource_type, username, region, resource_id){
    if (!resource_id)
      return null;

    var RESOURCE_PATHS = {
      'server': '/#compute%2CcloudServersOpenStack%2C',
      'legacy_server': '/#compute%2CcloudServers%2C',
      'load_balancer': '/load_balancers#rax%3Aload-balancer%2CcloudLoadBalancers%2C',
      'database': '/database#rax%3Adatabase%2CcloudDatabases%2C'
    };

    return 'https://mycloud.rackspace.com/a/' + username + RESOURCE_PATHS[resource_type] + region + '/' + resource_id;
  }

  scope.novaStatsURL = function(region, resource_id){
    if(region)
      return 'https://reports.ohthree.com/' + region.toLowerCase() + '/instance/' + resource_id;
  }

  scope.sshTo = function(address){
    return 'ssh://root@' + address;
  }

  function get_resource_type(resource) {
    if (!resource) return null;

    var resource_type;
    switch(resource.provider) {
      case 'nova':
        resource_type = 'server';
        break;
      case 'legacy':
        resource_type = 'legacy_server';
        break;
      case 'load-balancer':
        resource_type = 'load_balancer';
        break;
      case 'databases':
        resource_type = 'database';
        break;
      default:
        resource_type = null;
        break;
    }

    return resource_type;
  }

  scope.get_url = function(service, resource, tenant_id, username) {
    if (!scope.is_valid(resource)) return;

    var url;
    var resource_type = get_resource_type(resource);
    var resource_id = resource.instance.id;
    var region = resource.region || resource.instance.region;
    var address = resource.instance.public_ip;

    switch(service) {
      case 'cloud_control':
        url = scope.cloudControlURL(resource_type, resource_id, region, tenant_id);
        break;
      case 'my_cloud':
        url = scope.myCloudURL(resource_type, username, region, resource_id);
        break;
      case 'nova_stats':
        url = scope.novaStatsURL(region, resource_id);
        break;
      case 'ssh':
        url = scope.sshTo(address);
        break;
    }

    return url;
  }

  scope.is_valid = function(resource) {
    return get_resource_type(resource) != null;
  }

  return scope;
});

angular.module('checkmate.services').factory('Deployment', ['$http', "$resource", function($http, $resource){
  var scope = {};

  var get_resource_possible_ids = function(all_resources, current_resources, host_type) {
    var instance_ids = [];

    if (!current_resources)
      return instance_ids;

    if (!host_type) {
      instance_ids = instance_ids.concat( get_resource_possible_ids(all_resources, current_resources, 'hosts') );
      instance_ids = instance_ids.concat( get_resource_possible_ids(all_resources, current_resources, 'hosted_on') );
      return instance_ids;
    }

    if (!(current_resources instanceof Array))
      current_resources = [current_resources];

    for (var i=0 ; i<current_resources.length ; i++) {
      var resource = current_resources[i];

      if (resource) {
        instance_ids.push(resource.index);
        var nested_resources = resource[host_type];
        if (!nested_resources) continue;

        if (host_type == 'hosts') {
          for (var j=0 ; j<nested_resources.length ; j++) {
            var idx = nested_resources[j];
            instance_ids = instance_ids.concat( get_resource_possible_ids(all_resources, all_resources[idx], host_type) )
          }
        } else {
          instance_ids = instance_ids.concat( get_resource_possible_ids(all_resources, all_resources[nested_resources], host_type) )
        }
      }
    }

    return instance_ids;
  }

  var get_plan_instance_ids = function(deployment, service_name) {
    var instance_ids;

    try {
      instance_ids = deployment.plan.services[service_name].component.instances;
    } catch (err) {
      instance_ids = [];
    }

    return instance_ids;
  }

  var get_valid_resource_ids = function(deployment, resources) {
    var ids = []
    var all_resources = deployment.resources;

    for (var i=0 ; i<resources.length ; i++) {
      var resource = resources[i];
      var service_name = resource.service;
      var instance_ids = get_plan_instance_ids(deployment, service_name);
      var possible_ids = get_resource_possible_ids(all_resources, resources);

      for (var j=0 ; j<instance_ids.length ; j++) {
        var id = instance_ids[j];
        if (possible_ids.indexOf(id) > -1)
          ids.push(id);
      }

    }

    return _.uniq(ids);
  }

  var get_deployment_url = function(deployment, action) {
    var url = '/'+deployment.tenantId+'/deployments/'+deployment.id;

    if (action) {
      url += '/' + action;
    }

    return url;
  }

  var _get_resource_url = function(deployment, resource, action) {
    var deployment_url = get_deployment_url(deployment);
    var resource_url = deployment_url+'/resources/'+resource.index;

    if (action) {
      resource_url += '/' + action;
    }

    return resource_url;
  }

  scope.status = function(deployment) {
    var status = deployment.status;
    var stop_statuses = ['COMPLETE', 'ERROR'];

    // if there's an operation running, override status:
    if (deployment.operation && stop_statuses.indexOf(deployment.operation.status) === -1) {
      status = deployment.operation.type;
    }

    return status;
  }

  scope.progress = function(deployment){
    if(scope.status(deployment) === 'FAILED' || scope.status(deployment) === 'UP')
      return 100;
    if(!deployment.operation)
      return 0;
    return (deployment.operation.complete / deployment.operation.tasks) * 100;
  }

  scope.check = function(deployment) {
    var url = get_deployment_url(deployment, '+check');
    return $http.get(url);
  }

  scope.add_nodes = function(deployment, service_name, num_nodes) {
    var data = { service_name: service_name, count: num_nodes };
    var url = get_deployment_url(deployment, '+add-nodes');
    return $http.post(url, data);
  }

  scope.delete_nodes = function(deployment, service_name, num_nodes, resources) {
    if (!(resources instanceof Array))
      resources = [resources];

    var resource_ids = get_valid_resource_ids(deployment, resources);

    var data = { service_name: service_name, count: num_nodes, victim_list: resource_ids };
    var url = get_deployment_url(deployment, '+delete-nodes');
    return $http.post(url, data);
  }

  scope.available_services = function(deployment) {
    var available_services = [];
    var services;
    try {
      services = deployment.blueprint.services;
    } catch (err) {}
    if (!services) return available_services;

    for (service_name in services) {
      var service = services[service_name];
      var constraints = service.constraints;
      if (!constraints) continue;

      for (var i=0 ; i<constraints.length ; i++) {
        var constraint = constraints[i];
        if ('setting' in constraint && constraint.setting == 'count') {
          available_services.push(service_name)
        }
      }
    }

    return available_services;
  }

  scope.take_offline = function(deployment, resource) {
    var data = {};
    var url = _get_resource_url(deployment, resource, '+take-offline');
    return $http.post(url, data);
  }

  scope.bring_online = function(deployment, resource) {
    var data = {};
    var url = _get_resource_url(deployment, resource, '+bring-online');
    return $http.post(url, data);
  }

  scope.sync =  function(deployment, success_callback, error_callback){
    var url = "/"+deployment.tenantId+"/deployments/"+deployment.id+"/+sync";
    return $http.get(url);
  }

  scope.parse =  function(deployment, tenant_id, success_callback, error_callback){
    var Parse = $resource((checkmate_server_base || '') + '/:tenantId/deployments/:deployment_id/+parse.json', null, {'get': {method:'GET'}});
    var parse = new Parse(deployment);
    parse.$save({tenantId: tenant_id}, success_callback, error_callback)
  }

  scope.get_application = function(deployment, resource) {
    if (resource.type == 'application')
      return resource;

    var hosted_resources = resource.hosts;
    for (var i=0 ; i<hosted_resources.length ; i++) {
      var idx = hosted_resources[i];
      var current_resource = deployment.resources[idx];
      if (current_resource.type == 'application')
        return current_resource;
    }
  }

  return scope;
}]);

angular.module('checkmate.services').factory('Cache', function() {
  var scope = {};
  var CACHE_STORAGE = 'cmcache';
  var storage = JSON.parse(localStorage.getItem(CACHE_STORAGE) || "{}");

  scope.get = function(cache_name) {
    if (!storage[cache_name]) {
      storage[cache_name] = {};
    }

    storage[cache_name].save = function() {
      // Loads current cache to update only necessary values
      var current_cache = JSON.parse(localStorage.getItem(CACHE_STORAGE) || "{}");
      current_cache[cache_name] = storage[cache_name];
      localStorage.setItem(CACHE_STORAGE, JSON.stringify(current_cache));
    }

    return storage[cache_name];
  }

  return scope;
});

angular.module('checkmate.services').factory('WorkflowSpec', [function() {
  var DEFAULTS = {
    RESOURCE_TITLE_ATTR: 'dns-name',
    RESOURCE_ICON_ATTR: 'service',
    NO_RESOURCE: 9999,
    TASK_DURATION: 10,
    LOG_SCALE: 15,
    PADDING: 20,
    WIDTH: 0
  };

  var _is_invalid = function(spec, specs) {
    var is_custom_deployment = specs['end'];

    return (
         !spec
      || !spec.properties
      || spec.inputs.length == 0 && !is_custom_deployment
      || spec.inputs.length == 0 && spec.outputs.length == 0
    );
  }

  var _create_stream = function() {
    var stream = {
      icon: null,
      data: [],
      title: null,
      position: 0
    };
    return stream;
  }

  var _get_resource_icon = function(resource_id, deployment) {
    if (!deployment) return '';

    var resource = deployment.resources[resource_id];
    if (!resource) return '';

    var hosted_resources = resource.hosts;
    var icon;

    if (hosted_resources) {
      var first_resource = hosted_resources[0];
      icon = _get_resource_icon(first_resource, deployment);
    } else {
      icon = resource.type;
    }

    return icon;
  }

  var _get_resource_title = function(resource_id, deployment) {
    var title = '';
    if (!deployment) return title;

    var resource = deployment.resources[resource_id];
    if (resource) {
      title = resource[DEFAULTS.RESOURCE_TITLE_ATTR];
    }

    return title;
  }

  var _get_resource_id_from_inputs = function(inputs, specs) {
    var id = DEFAULTS.NO_RESOURCE;

    for (var i=0 ; i<inputs.length ; i++) {
      var input = inputs[i];
      var input_spec = specs[input];
      var resource_id = specs[input].properties.resource;
      if (resource_id) {
        id = resource_id;
        break;
      } else {
        id = _get_resource_id_from_inputs(input_spec.inputs, specs);
      }
    }

    return id;
  }

  var _get_distance_from_start = function(spec, all_specs, memo) {
    if(memo[spec.id]) {
      return memo[spec.id];
    }

    if(spec.id === 1){
      memo[spec.id] = 0;
      return memo[spec.id];
    }

    var max_spec_name = _.max(spec.inputs, function(input){
      return _get_distance_from_start(all_specs[input], all_specs, memo);
    });

    var max_duration = all_specs[max_spec_name].properties.estimated_duration || DEFAULTS.TASK_DURATION;
    memo[spec.id] = memo[all_specs[max_spec_name].id] + Math.log(max_duration) * DEFAULTS.LOG_SCALE;
    return memo[spec.id];
  }

  var _get_parent_resource_id = function(id, resources) {
    var resource_id;
    var resource = resources[id];
    if (!resource) return id;

    var host_id = resource.hosted_on;

    if (host_id)
      resource_id = _get_parent_resource_id(host_id, resources);
    else
      resource_id = id;

    return resource_id;
  }

  var _get_top_resource_id = function(spec, specs, deployment) {
    var resource_id;

    if (spec.properties.resource) {
      var id = spec.properties.resource;
      if (deployment) {
        resource_id = _get_parent_resource_id(id, deployment.resources);
      } else {
        resource_id = id;
      }
    }
    else {
      var id = _get_resource_id_from_inputs(spec.inputs, specs);
      resource_id = _get_parent_resource_id(id, deployment.resources);
    }

    return resource_id;
  }

  var _get_stream_position = function(resource_id, streams) {
    var position;

    if (resource_id === DEFAULTS.NO_RESOURCE) {
      position = 0;
    } else {
      position = streams.all.length;
      // Leave room for NO_RESOURCE stream if it doesn't exist yet
      if (!streams[DEFAULTS.NO_RESOURCE])
        position += 1;
    }

    return position;
  }

  var _offset_stream_position = function(streams) {
    // If stream DEFAULTS.NO_RESOURCE does not exist
    // offset all streams one position down
    if (streams[DEFAULTS.NO_RESOURCE]) return;

    for (var key in streams) {
      var stream = streams[key];
      if (!(stream instanceof Object && 'position' in stream)) continue;

      stream.position--;
      for (var j=0 ; j<stream.data.length ; j++) {
        var node = stream.data[j];
        node.position.y = stream.position;
      }
    }
  }

  var _build_links = function(specs, nodes) {
    var links = [];

    _.each(specs, function(spec, spec_name) {
      if (!spec) return;

      if(spec.outputs) {
        _.each(spec.outputs, function(output) {
          source = _.findWhere(nodes, { name: spec_name });
          target = _.findWhere(nodes, { name: output });
          if(source && target) {
            var link = {source: source, target: target}
            links.push(link);
          }
        });
      }
    });

    return links;
  }

  var scope = {};

  scope.to_streams = function(specs, deployment) {
    var position_memo = {}
    var streams = {};

    var sorted_keys = []
    for (var k in specs) {
      sorted_keys.push(k)
    }
    sorted_keys.sort()

    streams.all = [];
    streams.nodes = [];
    streams.links = [];
    streams.width = DEFAULTS.WIDTH;

    for (var idx in sorted_keys) {
      var key = sorted_keys[idx]
      var spec = specs[key];
      if (_is_invalid(spec, specs)) continue;

      var resource_id = _get_top_resource_id(spec, specs, deployment);
      var stream = streams[resource_id];
      if (!stream) {
        stream = _create_stream();
        stream.position = _get_stream_position(resource_id, streams);
        stream.title = _get_resource_title(resource_id, deployment);
        stream.icon = _get_resource_icon(resource_id, deployment);
        streams[resource_id] = stream;
        streams.all.push(stream);
      }

      spec.position = {};
      spec.position.stream = resource_id;
      spec.position.x = _get_distance_from_start(spec, specs, position_memo);
      spec.position.y = stream.position;
      stream.data.push(spec);
      streams.nodes.push(spec);

      if (spec.position.x > streams.width)
        streams.width = spec.position.x + DEFAULTS.PADDING;
    }

    streams.links = _build_links(specs, streams.nodes);
    _offset_stream_position(streams);

    return streams;
  }

  return scope;
}]);

angular.module('checkmate.services').factory('BlueprintHint', ['BlueprintDocs', function(BlueprintDocs) {
  var scope = {};

  var _blank_token = function(token) {
    return (token.type === null && token.string.trim() == "");
  }

  var _get_fold = function(_editor, line_number){
    var pos = CodeMirror.Pos(line_number);
    var mode = _editor.getOption('mode');
    var func = (mode == 'application/json') ? CodeMirror.fold.brace : CodeMirror.fold.indent;
    return func(_editor, pos)
  }

  scope.get_fold_tree = function(_editor, cursor, check_current_line) {
    var fold_tree = [];
    var current_fold = null;
    var current_cursor = cursor;
    var current_key;

    if (check_current_line === undefined)
      check_current_line = true;

    if (check_current_line)
      fold_tree.push(scope.get_key(_editor, cursor.line))

    while (true) {
      current_fold = scope.get_parent_fold(_editor, current_cursor);
      if (current_fold === undefined)
        break;
      current_key = scope.get_key(_editor, current_fold.from.line);
      if (current_key == "")
        break;

      fold_tree.push(current_key);
      current_cursor = current_fold.from;
    }

    return fold_tree.reverse();
  }

  scope.get_key = function(_editor, line_num) {
    var trimmed_key_line = _editor.getLine(line_num).trim();
    return trimmed_key_line.substring(0, trimmed_key_line.indexOf(":"));
  }

  scope.get_parent_fold = function(_editor, cursor, check_current_line) {
    var keep_going = true,
        start,
        fold_containing_cursor,
        current_fold;

    if (check_current_line) {
      start = cursor.line
    } else {
      start = cursor.line-1
    }

    angular.forEach(_.range(start, -1, -1), function(num){
      if (!keep_going)
        return

      current_fold = _get_fold(_editor, num);
      if(current_fold) {
        if (current_fold.to.line >= cursor.line){
          fold_containing_cursor = current_fold
          keep_going = false;
        }
      }
    })
    return fold_containing_cursor;
  }

  scope.get_parent_fold_key = function(_editor, cursor, check_current_line){
    var fold = scope.get_parent_fold(_editor, cursor, check_current_line)
    if (fold === undefined) return "";
    return scope.get_key(_editor, fold.from.line);
  }

  scope.hinting = function(_editor) {
    var cursor = _editor.getCursor();
    var token = _editor.getTokenAt(cursor);
    var keys = BlueprintDocs.keys( scope.get_fold_tree(_editor, cursor, false), token );
    var position = _blank_token(token) ? cursor.ch : token.start;
    if (token.type && token.type.indexOf('string') > -1)
      position++;

    return {
      list: keys || [],
      from: CodeMirror.Pos(cursor.line, position),
      to: CodeMirror.Pos(cursor.line, cursor.ch)
    }
  }

  return scope;
}]);

angular.module('checkmate.services').provider('BlueprintDocs', [function() {
  var _any_key = 'any';
  var _text_key = '_';
  var _docs = {};
  var scope = {};
  var provider = {};

  var _wrap_docs = function(doc) {
    return {
      text: function() { return doc[_text_key]; }
    };
  }

  var _find_doc = function(path_tree) {
    var doc = _docs;
    var current_doc = _docs;
    var _path_tree = angular.copy(path_tree);
    var current_path = _path_tree.shift();

    while (current_path) {
      current_path = current_path.replace(/"/g, '');
      doc = current_doc[current_path] || current_doc[_any_key];
      if (!doc) {
        doc = {};
        break;
      }
      current_path = _path_tree.shift();
      current_doc = doc;
    }

    return doc;
  }

  // ===== Scope =====
  scope.find = function(path_tree) {
    return _wrap_docs(_find_doc(path_tree));
  }

  scope.keys = function(path_tree, partial_token) {
    var filter_partial = function(elem) {
      var text = partial_token.string.trim().replace(/['"]/g, '');
      if (elem.indexOf(text) == 0)
        return true;
    }

    var _doc = _find_doc(path_tree);
    var doc = angular.copy(_doc);
    delete doc[_any_key];
    delete doc[_text_key];
    var keys = Object.keys(doc).sort();

    return _.filter(keys, filter_partial);
  }

  // ===== Provider =====
  provider.docs = function(filename) {
    provider._filename = filename;
  }

  provider.any_key = function(any_key) {
    _any_key = any_key;
  }

  provider.text_key = function(text_key) {
    _text_key = text_key;
  }

  provider.$get = function($http) {
    $http.get(provider._filename).then(function(response){
      try {
        _docs = jsyaml.safeLoad(response.data);
      } catch(err) {
        console.log("YAML file for Blueprint documentation could not be parsed");
      }
    });
    return scope;
  }

  return provider;
}]);

angular.module('checkmate.services').factory('DeploymentTree', [function() {
  var scope = {};

  var VERTEX_GROUPS = {
    // Standard architecture
    lb: 0,
    master: 1,
    web: 1,
    app: 1,
    admin: 1,
    backend: 2,

    // Cassandra
    seed: 0,
    node: 1,
    'region-two': 2,

    // Mongo
    primary: 0,
    data: 1
  };

  var _create_vertex = function(resource, resource_list) {
    var group = resource.service;
    var dns_name = resource['dns-name'] || '';
    var name = dns_name.split('.').shift();
    var host_id = resource.hosted_on;
    var host = resource_list[host_id];

    var vertex = {
      id: resource.index,
      group: group,
      component: resource.component,
      name: name,
      status: resource.status,
      host: {},
      service: resource.service,
      index: resource.index,
      'dns-name': resource['dns-name']
    };
    if (host) {
      vertex.host = {
        id: host.index,
        status: host.status,
        type: host.component
      };
    }
    return vertex;
  };

  var _create_edges = function(vertex, relations) {
    var edges = [];

    var v1 = vertex.id;
    for (var i in relations) {
      var relation = relations[i];
      if (relation.relation != 'reference') continue;

      var v2 = relation.source || relation.target;
      var sorted_edges = [v1, v2].sort();
      var edge = { v1: sorted_edges[0], v2: sorted_edges[1] };
      edges.push(edge);
    }

    return edges;
  }

  scope.build = function(deployment) {
    var edges = [];
    var vertices = [];
    var resources = deployment.resources;

    for (var i in resources) {
      var resource = resources[i];
      if (!resource.relations) continue;

      // Vertices
      var vertex = _create_vertex(resource, resources);
      var group_idx = VERTEX_GROUPS[vertex.group] || 0;
      if (!vertices[group_idx]) vertices[group_idx] = [];
      vertices[group_idx].push(vertex);

      // Edges
      edges = edges.concat(_create_edges(vertex, resource.relations));
    }

    return { vertex_groups: vertices, edges: edges };
  }

  return scope;
}]);

angular.module('checkmate.services').factory('DelayedRefresh', ['$timeout', function($timeout) {

  var scope = {};

  /*
   This creates an object with a refresh method.  This method takes a callback which will
   be executed only after the given timeout expires. If refresh is called again before the
   timeout expires, the timeout is reset and the callback execution is delayed further.

   This allows for responsive callbacks while still keeping expensive calls at a minimum.
   */

  scope.get_instance = function(callback, timeout) {
    var _scope = {};

    _scope.callback = callback;
    _scope.timeout = timeout || 2000;
    _scope.timeout_handle = null;

    _scope.reset = function(value) {
      if (_scope.timeout_handle) {
        $timeout.cancel(_scope.timeout_handle);
      }
      _scope.timeout_handle = null;
      return value;
    }

    _scope.start = function(callback) {
      _scope.timeout_handle = $timeout(callback || _scope.callback, _scope.timeout);
      return _scope.timeout_handle.then(_scope.reset);
    }

    _scope.refresh = function(callback) {
      _scope.reset();
      return _scope.start(callback);
    }

    return _scope;
  }

  return scope;

}]);
