var directives = angular.module('checkmate.directives', ["template/popover/popover-html-unsafe-popup.html"]);

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
    scope: {content: '@content', swf: '@swf', bgcolor: '@bgcolor', clipElement: '@clippyElement' },
    compile: function(tElement, tAttrs, transclude) {
        return {
            post: function(scope, elm, attrs, ctrl) {
                // observe changes to interpolated attribute and only add sources when we have data

                function appendClipping(value){
                  if (scope.content) {
                    var clippy_html = '<object classid="clsid:d27cdb6e-ae6d-11cf-96b8-444553540000"\
                                width="110"\
                                height="14">\
                        <param name="allowScriptAccess" value="always" />\
                        <param name="quality" value="high" />\
                        <param name="scale" value="noscale" />\
                        <param name="movie" value="' + (scope.swf || "/libs/clippy/clippy.swf") + '">\
                        <param NAME="FlashVars" value="text=' + encodeURIComponent(scope.content) + '">\
                        <embed src="' + (scope.swf || "/libs/clippy/clippy.swf") + '"\
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
                }

                attrs.$observe('content', appendClipping);
                attrs.$observe('clippyElement', function(value) {
                  if(value) {
                    angular.element(elm).attr('content', angular.element(value).text());
                    scope.content = angular.element(value).text();
                  }
                  appendClipping(value);
                });
            }
        };
    }
  };
  return directiveDefinitionObject;
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

directives.directive('cmTreeView', function() {
  var create_svg = function(scope, element, attrs) {
    scope.width = attrs.width || 256;
    scope.height = attrs.height || 256;

    if (!scope.svg) {
      scope.svg = d3.select(element[0])
        .append('svg:svg')
        .attr('id', attrs.id)
        .attr('viewBox', [0, 0, scope.width, scope.height].join(' '));

      scope.svg.append('svg:g').attr('class', 'edges');
      scope.svg.append('svg:g').attr('class', 'vertices');
    }
  }

  var get_vertex_data = function(vertex_groups, scope) {
    var data = {};
    var groups = vertex_groups;
    var num_groups = groups.length;
    var group_height = scope.height / num_groups;
    var group_center = group_height / 2;
    for (var i=0 ; i<num_groups ; i++) {
      var vertices = groups[i];
      if (!vertices) continue;
      var num_vertices = vertices.length;
      var vertex_width = scope.width / num_vertices;
      var vertex_center = vertex_width / 2;
      for (var j=0 ; j<num_vertices ; j++) {
        var vertex = vertices[j];
        vertex.x = vertex_center + vertex_width * j;
        vertex.y = group_center + group_height * i;
        data[vertex.id] = vertex;
      }
    }
    return data;
  }

  var get_color = function(status) {
    if (!status) return null;

    var color;
    switch(status) {
      case "ACTIVE":
        color = 'green';
        break;
      case 'NEW':
      case 'BUILD':
      case 'DELETING':
      case 'CONFIGURE':
        color = 'orange';
        break;
      case 'ERROR':
        color = 'red';
        break;
      case 'DELETED':
        color = 'black';
        break;
      case "PLANNED":
      default:
        color = 'gray';
        break;
    }
    return color;
  }

  var get_icon = function(vertex) {
    var icon = null;
    var base_dir = '/img/icons/';
    switch(vertex.group) {
      case 'web':
      case 'seed':
      case 'node':
      case 'master':
        icon = 'compute';
        break;
      case 'lb':
        icon = 'load-balancer';
        break;
      case 'backend':
        icon = 'database';
        break;
      default:
        icon = 'compute';
        break;
    }
    color = get_color(vertex.host.status || vertex.status);
    if (icon)
      icon = [base_dir, icon, '-', color, '.svg'].join('');

    return icon;
  }

  var update_svg = function(new_data, old_data, scope) {
    if (!new_data) new_data = {};
    var vertex_data = get_vertex_data(new_data.vertex_groups, scope);
    var vertices = scope.svg.select('g.vertices').selectAll('.vertex')
      .data(_.values(vertex_data), function(d) { return d.id; });

    // Update
    vertices.select('image')
      .attr('xlink:href', get_icon);
    vertices.select('circle')
      .attr('r', function(d) { if (d.host.id) return 8; })
      .attr('cy', -20)
      .attr('fill', function(d) { return get_color(d.status); });
    // Enter
    var vertex = vertices.enter()
      .append('svg:g')
      .attr('class', 'vertex')
      .attr('transform', function(d) {
        return ['translate(', d.x, ',', d.y, ')'].join('');
      });
    vertex
      .append('svg:text')
      .attr('text-anchor', 'middle')
      .attr('y', 20)
      .text(function(d) { return d.name; });
    vertex
      .append('svg:circle')
      .attr('r', function(d) { if (d.host.id) return 8; })
      .attr('cy', -20)
      .attr('fill', function(d) { return get_color(d.status); })
      .append('svg:title')
        .text(function(d) { return d.component; });
    vertex
      .append('svg:image')
      .attr('xlink:href', get_icon)
      .attr('class', function(d) { return d.group })
      .attr('x', '-16px')
      .attr('y', '-16px')
      .attr('width', '32px')
      .attr('height', '32px');

    // Exit
    vertices.exit().remove();

    var edges = scope.svg.select('g.edges').selectAll('.edge')
      .data(new_data.edges);

    // Enter
    edges.enter()
      .append('svg:line')
      .attr('class', 'edge')
      .attr('x1', function(d) { return vertex_data[d.v1].x })
      .attr('y1', function(d) { return vertex_data[d.v1].y })
      .attr('x2', function(d) { return vertex_data[d.v2].x })
      .attr('y2', function(d) { return vertex_data[d.v2].y });
    // Exit
  }

  return {
    restrict: 'E',
    replace: true,
    scope: { data: '=' },
    link: function(scope, element, attrs) {
      create_svg(scope, element, attrs);
      scope.$watch('data', update_svg);
    }
  };
});

angular.module('checkmate.directives').directive('cmNotifications', ['$rootScope', function($rootScope) {
  var flush_notifications = function(new_messages, old_messages, scope) {
    if (!new_messages) return;

    var options = {
      message: { text: null },
      fadeOut: { enabled: true, delay: 5000 },
      type: 'bangTidy'
    };

    while (new_messages.length > 0) {
      var msg = new_messages.shift();
      options.message.text = msg;
      scope.element.notify(options).show();
    }
  }

  return {
    restrict: 'A',
    scope: { cmNotifications: '=' },
    link: function(scope, element, attrs) {
      scope.element = element;
      scope.$watch('cmNotifications', flush_notifications, true);
    }
  };
}]);

// Extend ui-bootstrap to use HTML popovers
directives.directive( 'popoverHtmlUnsafePopup', function () {
  return {
    restrict: 'E',
    replace: true,
    scope: { content: '@', placement: '@', animation: '&', isOpen: '&' },
    templateUrl: 'template/popover/popover-html-unsafe-popup.html'
  };
});

directives.directive( 'popoverHtmlUnsafe', [ '$tooltip', function ( $tooltip ) {
  return $tooltip( 'popoverHtmlUnsafe', 'popover', 'click' );
}]);

angular.module("template/popover/popover-html-unsafe-popup.html", []).run(["$templateCache", function($templateCache) {
  $templateCache.put("template/popover/popover-html-unsafe-popup.html",
    "<div class=\"popover {{placement}}\" ng-class=\"{ in: isOpen(), fade: animation() }\">\n" +
    "  <div class=\"arrow\"></div>\n" +
    "\n" +
    "  <div class=\"popover-inner\">\n" +
    "      <h3 class=\"popover-title\" ng-bind-html-unsafe=\"title\" ng-show=\"title\"></h3>\n" +
    "      <div class=\"popover-content\" ng-bind-html-unsafe=\"content\"></div>\n" +
    "  </div>\n" +
    "</div>\n" +
    "");
}]);
