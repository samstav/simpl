var directives = angular.module('checkmate.directives', []);

//New HTML tag hard-coded for use in New Deployment Form to display options
directives.directive('cmOption', function($compile) {
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
});

directives.directive('clippy', function factory() {
  var directiveDefinitionObject = {
    priority: 0,
    template: '<span></span>',
    controller: function($scope) {
        $scope.encode = function(data) {
            return encodeURIComponent(data);
            };
    },
    replace: true,
    transclude: false,
    restrict: 'E',
    scope: {content: '@content', swf: '@swf', bgcolor: '@bgcolor'},
    compile: function(tElement, tAttrs, transclude) {
        return {
            post: function(scope, elm, attrs, ctrl) {
                // observe changes to interpolated attribute and only add sources when we have data
                attrs.$observe('content', function(value) {
                  if (value) {
                    var clippy_html = '<object classid="clsid:d27cdb6e-ae6d-11cf-96b8-444553540000"\
                                width="110"\
                                height="14">\
                        <param name="allowScriptAccess" value="always" />\
                        <param name="quality" value="high" />\
                        <param name="scale" value="noscale" />\
                        <param name="movie" value="' + (scope.swf || "/static/libs/clippy/clippy.swf") + '">\
                        <param NAME="FlashVars" value="text=' + encodeURIComponent(scope.content) + '">\
                        <embed src="' + (scope.swf || "/static/libs/clippy/clippy.swf") + '"\
                               width="110"\
                               height="14"\
                               name="clippy"\
                               quality="high"\
                               allowScriptAccess="always"\
                               type="application/x-shockwave-flash"\
                               pluginspage="http://www.macromedia.com/go/getflashplayer"\
                               FlashVars="text=' + encodeURIComponent(scope.content) + '"\
                               bgcolor="' + scope.bgcolor +'"\
                        />\
                        </object>'
                    elm.children('object').remove();
                    elm.append(clippy_html);
                  }
                });
            }
        };
    }
  };
  return directiveDefinitionObject;
});

directives.directive('popover', function(){
  return function(scope, element, attrs) {
    var popover = element.popover({
      content: function() {
        if ('target' in attrs)
          if ($(attrs['target']).length > 0)
            return $(attrs['target']).html();
      }
    });

    //Update when scope changes
    if ('target' in attrs) {
      scope.$parent.$watch(function() {
        if ($(attrs['target']).length > 0 && popover.data('popover') !== undefined) {
          popover.data('popover').setContent($(attrs['target']).html());
          popover.data('popover').$tip.addClass(popover.data('popover').options.placement);
        }
      });
    }
  };
});

//Validates a control against the supplied option's constraints and sets the
//constraint.valid and option.invalid values
directives.directive('validateOption', function () {
  return {
    restrict: 'A',
    require: 'ngModel',
    link: function (scope, elm, attrs, ctrl) {
      var option = scope[attrs.validateOption];

      function validate(value) {
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
        //FIXME: hack! dynamically generated control validation is not bubbling up otherwise
        angular.element($('#newDeploymentForm')).scope().newDeploymentForm.$setValidity(error_key, valid, ctrl);
        option.invalid = !valid;
        return valid ? value : undefined;
      }

      //For DOM -> model validation
      ctrl.$parsers.unshift(function(viewValue) {
          return validate(viewValue) ? viewValue : undefined;
      });

      //For model -> DOM validation
      ctrl.$formatters.unshift(function(value) {
        validate(value);
        return value;
      });
    }
  };
});
