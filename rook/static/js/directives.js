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
  var DEFAULTS = {
    HIGHLIGHT_NODE: 'highlight',
    HIGHLIGHT_GRAD_ID: 'highlight_gradient',
    HIGHLIGHT_GRAD_COLOR: '#0E90D2',
    HIGHLIGHT_RADIUS: 30,
    NOT_SCALABLE_MSG: 'This service cannot be scaled'
  }
  var create_svg = function(scope, element, attrs) {
    scope.width = attrs.width || 256;
    scope.height = attrs.height || 256;
    element.css('max-height', scope.height + 'px');
    element.css('max-width', scope.width + 'px');

    if (!scope.svg) {
      scope.svg = d3.select(element[0])
        .append('svg:svg')
        .attr('id', attrs.id)
        .attr('viewBox', [0, 0, scope.width, scope.height].join(' '));

      scope.svg.append('svg:g').attr('class', 'edges');
      scope.svg.append('svg:g').attr('class', 'vertices');

      var gradient = scope.svg.append("svg:defs")
      .append("svg:radialGradient")
      .attr("id", DEFAULTS.HIGHLIGHT_GRAD_ID)

      gradient.append("svg:stop")
      .attr("offset", "0%")
      .attr("stop-color", DEFAULTS.HIGHLIGHT_GRAD_COLOR)
      .attr("stop-opacity", 1);

      gradient.append("svg:stop")
      .attr("offset", "100%")
      .attr("stop-color", DEFAULTS.HIGHLIGHT_GRAD_COLOR)
      .attr("stop-opacity", 0);
    }
  }

  var select_node = function(node, scope, element) {
    if (!scope.selectNode) return;

    var toggled = scope.$apply(function() { return scope.selectNode(node); });
    if (toggled) {
      toggle_highlight(node, element);
    }
  }

  var toggle_highlight = function(node, element) {
    var d3_element = d3.select(element);
    var highlight_node = d3_element.select('.' + DEFAULTS.HIGHLIGHT_NODE);
    var has_highlight = highlight_node[0][0];
    if (has_highlight) {
      highlight_node.remove();
    } else {
      d3_element
        .insert('circle', ':first-child')
        .attr('class', DEFAULTS.HIGHLIGHT_NODE)
        .attr('r', DEFAULTS.HIGHLIGHT_RADIUS)
        .style('fill', 'url(#'+DEFAULTS.HIGHLIGHT_GRAD_ID+')')
        //.attr("transform", function() { return "translate(" + x + "," + y + ")"; })
        ;
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

  var _add_tooltips = function(node, scope, element) {
    if (!scope.clickableNode) return;

    var is_scalable_service = scope.clickableNode(node);
    if (is_scalable_service) return;

    angular.element(element).tipsy({
      gravity: 'e',
      html: true,
      title: function() {
        return DEFAULTS.NOT_SCALABLE_MSG;
      }
    });
  }

  var update_svg = function(new_data, old_data, scope) {
    if (!new_data) new_data = {};
    var vertex_data = get_vertex_data(new_data.vertex_groups, scope);
    var vertices = scope.svg.select('g.vertices').selectAll('.vertex')
      .data(_.values(vertex_data), function(d) { return d.id; });

    // Update
    vertices
      .attr('transform', function(d) {
        return ['translate(', d.x, ',', d.y, ')'].join('');
      });
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
      .on('click', function(d) { select_node(d, scope, this); })
      .style('cursor', 'pointer')
      .each(function(d) { _add_tooltips(d, scope, this); })
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
    edges
      .attr('x1', function(d) { return vertex_data[d.v1].x })
      .attr('y1', function(d) { return vertex_data[d.v1].y })
      .attr('x2', function(d) { return vertex_data[d.v2].x })
      .attr('y2', function(d) { return vertex_data[d.v2].y });
    // Enter
    edges.enter()
      .append('svg:line')
      .attr('class', 'edge')
      .attr('x1', function(d) { return vertex_data[d.v1].x })
      .attr('y1', function(d) { return vertex_data[d.v1].y })
      .attr('x2', function(d) { return vertex_data[d.v2].x })
      .attr('y2', function(d) { return vertex_data[d.v2].y });
    // Exit
    edges.exit().remove();
  }

  return {
    restrict: 'E',
    template: '<div class="deployment_tree"></div>',
    replace: true,
    scope: {
      data: '=',
      selectNode: '=',
      clickableNode: '='
    },
    link: function(scope, element, attrs) {
      create_svg(scope, element, attrs);
      scope.$watch('data', update_svg);
    }
  };
});

directives.directive('cmWorkflow', ['WorkflowSpec', function(WorkflowSpec) {
  var DEFAULTS = {
    TOTAL_HEIGHT: 100,
    SVG_HEIGHT: 100,
    SVG_WIDTH: 300,
    NODE_RADIUS: 1.5,
    NODE_HEIGHT: 3,
    HIGHLIGHT_NODE: 'highlight',
    AVAILABLE_ICONS: ['compute', 'load-balancer', 'database'],
    ICON_FOLDER: '/img/icons/',
    ICON_HEIGHT: 8,
    ICON_WIDTH: 8,
    ICON_MARGIN: 4,
    TEXT_MARGIN: 3
  };

  var _even_odd = function(num) {
    return num % 2 == 0 ? 'even' : 'odd';
  }

  var _node_color = function(d, scope) {
    var color;
    var state = scope.status(d.name);
    switch(scope.state({state: state})) {
      case "Ready":
      case "Completed":
        color = 'green';
        break;
      case "Waiting":
        color = 'orange';
        break;
      case "Error":
        color = 'red';
        break;
      case "Future":
      case "Likely":
      case "Maybe":
        color = 'gray';
        break;
      default:
        color = 'black';
        break;
    }
    return color;
  }

  var _get_icon = function(d) {
    var icon;

    if (d.icon) {
      icon = DEFAULTS.ICON_FOLDER + d.icon + '-gray.svg';
    }

    return icon;
  }

  var _update_specs = function(new_value, old_value, scope) {
    scope.specs = new_value;
    update_svg(scope);
  }

  var _update_deployment = function(new_value, old_value, scope) {
    scope.deployment = new_value;
    update_svg(scope);
  }

  var _interpolate_node = function(x, new_width, old_width) {
    var padded_width = new_width - DEFAULTS.ICON_WIDTH;
    return x * padded_width / old_width + DEFAULTS.ICON_WIDTH;
  }

  var _is_stream = function(stream) {
    return ( stream instanceof Object && 'position' in stream );
  }

  var _get_stream = function(streams, id) {
    return streams[id];
  }

  var _calculate_stream_heights = function(streams, positions) {
    var stream_height = DEFAULTS.TOTAL_HEIGHT / streams.all.length;
    streams.custom_height = 0;
    var num_custom_heights = 0;
    for (id in positions) {
      var row = positions[id];
      var num_nodes = row.length;
      var some_node = row[0];
      var stream = _get_stream(streams, some_node.position.stream);
      if (num_nodes > 1 && !('height' in stream)) {
        var custom_height = num_nodes * DEFAULTS.NODE_HEIGHT;
        if (custom_height > stream_height) {
          streams.custom_height += custom_height;
          stream.height = custom_height;
          num_custom_heights++;
        }
      }
    }

    var num_remaining_streams = streams.all.length - num_custom_heights;
    var remaining_height = DEFAULTS.TOTAL_HEIGHT - streams.custom_height;
    var remaining_stream_height = remaining_height / num_remaining_streams;

    for (var key in streams) {
      var stream = streams[key];
      if (!_is_stream(stream)) continue;
      if (stream.height) continue;

      stream.height = remaining_stream_height;
    }
  }

  var _sort_streams = function(streams) {
    var _by_position = function(stream) {
      return stream.position;
    }
    var stream_info = [];
    for (var key in streams) {
      var stream = streams[key];
      if (_is_stream(stream))
        stream_info.push(stream);
    }
    return _.sortBy(stream_info, _by_position);
  }

  var _avoid_node_collision = function(streams, positions) {
    for (id in positions) {
      var row = positions[id];
      var num_nodes = row.length;
      var some_node = row[0];
      var stream = _get_stream(streams, some_node.position.stream);
      if (num_nodes > 1) {
        var total_height = num_nodes * DEFAULTS.NODE_HEIGHT;
        var start_position = (stream.height - total_height) / 2;
        var current_position = start_position;
        for (var i=0 ; i<num_nodes ; i++) {
          var node = row[i];
          node.interpolated_position.y = current_position + DEFAULTS.NODE_HEIGHT / 2;
          current_position += DEFAULTS.NODE_HEIGHT;
        }
      }
    }
  }

  var _interpolate_streams = function(streams) {
    var current_stream_position = 0;

    for (var i=0 ; i<streams.length ; i++) {
      var stream = streams[i];
      stream.interpolated_position = current_stream_position;
      for (var j=0 ; j<stream.data.length ; j++) {
        var node = stream.data[j];
        if (!node.interpolated_position.hasOwnProperty('y')) {
          node.interpolated_position.y = stream.height / 2;
        }
        node.interpolated_position.y += current_stream_position;
      }
      current_stream_position += stream.height;
    }
  }

  var _calculate_node_position = function(streams, scope) {
    var positions = {};
    var num_streams = streams.all.length;
    var stream_height = DEFAULTS.TOTAL_HEIGHT / num_streams;

    for (var i=0 ; i<streams.nodes.length ; i++) {
      var node = streams.nodes[i];
      var x = _interpolate_node(node.position.x, scope.svg.width, streams.width);
      var y = node.position.y;
      var id = [x, y].join('--');
      node.interpolated_position = { x: x };

      if (!positions[id]) { positions[id] = []; }
      positions[id].push(node);
    }

    _calculate_stream_heights(streams, positions);
    _avoid_node_collision(streams, positions);
    var sorted_streams = _sort_streams(streams);
    _interpolate_streams(sorted_streams);
  }

  var _draw_highlight = function(d, scope, element) {
    var x = d.interpolated_position.x;
    var y = d.interpolated_position.y;

    d3.select('#' + DEFAULTS.HIGHLIGHT_NODE).remove();
    d3.select(element.parentNode)
      .insert('circle', ':first-child')
      .attr('id', DEFAULTS.HIGHLIGHT_NODE)
      .attr('r', DEFAULTS.NODE_RADIUS * 3)
      .attr("transform", function() { return "translate(" + x + "," + y + ")"; })
      .style('fill', 'url(#gradient)');

    if (scope.select)
      scope.select(d.name);
  }

  var _draw_background = function(elements, streams) {
    var num_streams = streams.all.length;
    var height = DEFAULTS.TOTAL_HEIGHT / num_streams;

    // Enter
    var stream = elements.enter()
      .append('svg:g')
      .attr('class', function(d) { return 'stream ' + _even_odd(d.position); })
      .attr('transform', function(d) {
        return 'translate(0, '+ d.interpolated_position +')';
      });
    stream.append('svg:rect')
      .attr('class', 'border')
      .attr('width', '100%')
      .attr('height', function(d) { return d.height; });
    stream.append('svg:image')
      .attr('xlink:href', _get_icon)
      .attr('x', DEFAULTS.ICON_MARGIN)
      .attr('y', function(d) { return (d.height - DEFAULTS.ICON_HEIGHT) / 2 })
      .attr('width', DEFAULTS.ICON_WIDTH + 'px')
      .attr('height', DEFAULTS.ICON_HEIGHT + 'px');
    stream.append("text")
      .attr("class", "nodetext")
      .attr("dx", DEFAULTS.TEXT_MARGIN)
      .attr("dy", function(d) { return (d.height - DEFAULTS.ICON_HEIGHT) / 2 + DEFAULTS.ICON_HEIGHT })
      .text(function(d) { return d.title.split('.').shift(); });

    // Exit
    elements.exit().remove();
  }

  var _draw_links = function(elements, streams, scope) {
    // Enter
    var stream_elements = elements.enter()
      .append('svg:line')
      .attr('class', 'link')
      .attr('x1', function(d) { return d.source.interpolated_position.x; })
      .attr('y1', function(d) { return d.source.interpolated_position.y; })
      .attr('x2', function(d) { return d.target.interpolated_position.x; })
      .attr('y2', function(d) { return d.target.interpolated_position.y; })
      ;

    // Exit
    elements.exit().remove();
  }

  var _add_tooltips = function(collection) {
      angular.element(collection[0]).tipsy({
      gravity: 'e',
      html: true,
      title: function() {
        return this.__data__.name;
      }
    });
  }

  var _draw_nodes = function(elements, streams, scope) {
    // Enter
    elements.enter()
      .append('svg:circle')
      .attr('class', 'node')
      .attr('name', function(d) { return d.name })
      .attr('cursor', 'pointer')
      .attr('r', DEFAULTS.NODE_RADIUS)
      .call(_add_tooltips)
      .attr("transform", function(d) {
        return "translate(" + d.interpolated_position.x + "," + d.interpolated_position.y + ")";
      })
      .on('click', function(d) { return _draw_highlight(d, scope, this); });
    // Update
    elements.style('fill', function(d) { return _node_color(d, scope); });
  }

  var create_svg = function(element, attrs) {
    var svg = {};
    svg.width = attrs.width || DEFAULTS.SVG_WIDTH;
    svg.height = attrs.height || DEFAULTS.SVG_HEIGHT;

    svg.element = d3.select(element[0])
      .append('svg:svg')
      .attr('viewBox', [0, 0, svg.width, svg.height].join(' '));

    svg.streams = svg.element.append('svg:g').attr('class', 'streams');
    svg.streams.append('svg:g').attr('class', 'background');
    svg.streams.append('svg:g').attr('class', 'links');
    svg.streams.append('svg:g').attr('class', 'nodes');


    var gradient = svg.element.append("svg:defs")
    .append("svg:radialGradient")
    .attr("id", "gradient")

    gradient.append("svg:stop")
    .attr("offset", "0%")
    .attr("stop-color", "#0E90D2")
    .attr("stop-opacity", 1);

    gradient.append("svg:stop")
    .attr("offset", "100%")
    .attr("stop-color", "#0E90D2")
    .attr("stop-opacity", 0);


    return svg;
  }

  var update_svg = function(scope) {
    if (!scope.deployment || scope.deployment.$resolved == false) return;

    var streams = WorkflowSpec.to_streams(scope.specs, scope.deployment);
    var bg_elements = scope.svg.streams.select('.background').selectAll('.stream').data(streams.all);
    var node_elements = scope.svg.streams.select('.nodes').selectAll('.node').data(streams.nodes);
    var link_elements = scope.svg.streams.select('.links').selectAll('.link').data(streams.links);

    _calculate_node_position(streams, scope);
    _draw_background(bg_elements, streams);
    _draw_links(link_elements, streams, scope);
    _draw_nodes(node_elements, streams, scope);
  }

  var link_fn = function(scope, element, attrs) {
    scope.svg = create_svg(element, attrs);
    scope.$watch('specs', _update_specs);
    scope.$watch('deployment', _update_deployment, true);
  }

  return {
    restrict: 'E',
    template: '<div class="cm-workflow"></div>',
    replace: true,
    scope: {
      specs: '=',
      deployment: '=',
      select: '=',
      status: '=',
      state: '='
    },
    link: link_fn
  };
}]);

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

angular.module('checkmate.directives').directive('cmStopClickPropagation', ['$rootScope', function($rootScope) {
  return {
    link: function(scope, element, attrs) {
      element.click(function(e) { e.stopPropagation(); });
    }
  };
}]);

angular.module('checkmate.directives').directive('cmPasswordManager', ['$rootScope', function($rootScope) {
  return {
    require: ['ngModel'],
    link: function(scope, element, attrs, controllers) {
      element.on('change', function(e) {
        var modelCtrl = controllers[0];
        modelCtrl.$setViewValue(element.val());
      })
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
