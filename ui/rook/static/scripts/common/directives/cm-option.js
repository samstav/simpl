angular.module('waldo.options', [])
.directive('cmOption', function($compile) {
  //New HTML tag hard-coded for use in Options Form to display options
  return {
    restrict: 'E',
    scope: false,
    replace: true,
    link: function(scope, element, attrs) {
      var option = scope.option;
      var message;
      var template = '';
      if (!option) {
        message = "The requested option is null";
        console.log(message);
        template = "<em>" + message + "</em>";
      } else if (!option.type || !_.isString(option.type)) {
        message = "The requested option '" + option.id + "' has no type or the type is not a string.";
        console.log(message);
        template = "<em>" + message + "</em>";
      } else {
        var lowerType = option.type.toLowerCase().trim();

        if (option.label == "Domain") {
            option.choice = scope.domain_names;
        }

        if (lowerType == "select") {
          if ("choice" in option) {
            if (!_.isString(option.choice[0]))
              lowerType = lowerType + "-kv";
          }
        }
        template = $('#option-' + lowerType).html();
        if (template === null) {
          message = "No template for option type '" + option.type + "'.";
          console.log(message);
          template = "<em>" + message + "</em>";
        }
      }
      template = (template || "").trim();
      element.append($compile(template)(scope));
    }
  };
}).directive('validateOption', function () {
  //Validates a control against the supplied option's constraints and sets the
  //constraint.valid and option.invalid values

  return {
    restrict: 'A',
    require: 'ngModel',
    link: function (scope, elm, attrs, ctrl) {
      var option = scope[attrs.validateOption];

      scope.$watch(attrs.validateOption, function(){
        option = scope[attrs.validateOption];
      });

      function validate(value, elem) {
        //Check constraints
        var constraints = option.constraints;
        var index = 0;
        var valid = true;
        _.each(constraints, function(constraint) {
          if ('regex' in constraint) {
            var patt = new RegExp(constraint.regex);
            constraint.valid = patt.test(value || '');
          } else if ('protocols' in constraint) {
            constraint.valid = constraint.protocols.indexOf((value || '').split(":")[0]) > -1;
          } else {
            constraint.valid = true;
          }
          if (constraint.valid === false)
              valid = false;
          index += 1;
        });
        var error_key = 'constraints' + option.id.replace('-', '');
        ctrl.$setValidity(error_key, valid);
        var form_name = elem.closest('form').attr('name');
        var form_scope = angular.element(elem).scope();
        form_scope[form_name].$setValidity(error_key, valid, ctrl);
        option.invalid = !valid;
        return valid ? value : undefined;
      }

      //For DOM -> model validation
      ctrl.$parsers.unshift(function(viewValue) {
          return validate(viewValue, elm) ? viewValue : undefined;
      });

      //For model -> DOM validation
      ctrl.$formatters.unshift(function(value) {
        validate(value, elm);
        return value;
      });
    }
  };
}).value('options', {
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
      if (region_option === null && (key == 'region' || option.type == 'region') && dh === undefined)
        region_option = option;

      var group;
      if (typeof dh !== 'undefined') {
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
        option.type = 'url';
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
          delete option.regex;
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
}).filter('capitalizeAll',
  function() {
    return function(input) {
      if(angular.isString(input) && input.length){
        var words = input.split(' ');
        var capital_words = [];
        _.each(words, function(word){
          capital_words.push(word.charAt(0).toUpperCase() + word.slice(1));
        });
        return capital_words.join(' ');
      }
      return input;
    };
  }
).filter('prepend', function() {
  return function(d, p) {
    if (d)
      return (p || "/") + d;
    return '';
  };
}).filter('cm_validation_rules', function() {
  return function(constraints) {
    var html = '<div class=\"validation_rules\">';
    if (constraints) {
      for (var idx=0 ; idx<constraints.length ; idx++)
      {
        var icon_class = constraints[idx].valid ? 'icon-ok' : 'icon-remove';
        var msg_class  = constraints[idx].valid ? 'text-success' : 'text-error';
        var message    = constraints[idx].message || "";
        html += ''
              + '<div class=\"' + msg_class + '\">'
              + '<i class=\"' + icon_class + '\"></i>' + message
              + '</div>'
              ;
      }
    }
    html += '</div>';

    return html;
  };
});