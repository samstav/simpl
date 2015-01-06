angular.module('checkmate.Blueprint')
  .directive('blueprintTopology', function($window, Drag, Blueprint, $timeout, Catalog, Sizes) {
    return {
      restrict: 'E',
      replace: true,
      scope: {},
      controller: function($scope) {
        $scope.catalog = Catalog.get();
        $scope.components = Catalog.getComponents();

        $scope.getTattoo = function(componentId) {
          return (((Catalog.getComponent(componentId) || {})['meta-data'] || {})['display-hints'] || {}).tattoo || '';
        };

        $scope.select = function(selection) {
          $scope.$emit('topology:select', selection);
        };

        $scope.deselect = function(selection) {
          $scope.$emit('topology:deselect', selection);
        };

        $scope.remove = function(selection) {
          Blueprint.remove(selection);
        };

        $scope.sever = function(data) {
          Blueprint.sever(data);
        };

        $scope.connect = function() {
          var source = Drag.source.get() || {};
          var target = Drag.target.get() || {};

          Blueprint.connect(source.serviceId, target.serviceId, target.interface, target['connect-from']);
        };

        $scope.$on('blueprint:update', function(event, data) {
          $timeout(function() {
            $scope.blueprint = angular.copy(data);
          });
        });

        $window.addEventListener('resize', function () {
          $scope.$broadcast('window:resize');
        });
      },
      template: '<svg class="blueprint-topology" xmlns:xlink="http://www.w3.org/1999/xlink"></svg>',
      link: function(scope, element, attrs) {
        var parent = angular.element(element).parent()[0];
        var d3 = $window.d3;
        var mouse;
        var service;
        var component;
        var sizes = Sizes;

        var state = {
          linking: false,
          translation: [0, 0],
          scale: 1
        };

        var zoom = d3.behavior.zoom()
            .scaleExtent([0.2, 3])
            .on("zoom", zoomed);

        var drag = d3.behavior.drag()
            .origin(function(d) { return d; })
            .on("dragstart", dragstarted)
            .on("drag", dragged)
            .on("dragend", dragended);

        var linkerDrag = d3.behavior.drag()
            .origin(function(d) {
              var t = d3.select(this);
              return {x: t.attr("x"), y: t.attr("y")};
            })
            .on("dragstart", linkstarted)
            .on("drag", linkdragged)
            .on("dragend", linkended);

        var svg = d3.select(element[0]);

        var zoomer = svg.append('g')
            .attr("transform", "translate(0,0)")
            .call(zoom)
            .attr('class', 'zoomer')
            .on('click', function(d) {
              if(d3.event.defaultPrevented) {
                return;
              }
              toggleSelect(d3.select(this), null);
            });

        var rect = zoomer.append("rect")
            .style("fill", "none")
            .style("pointer-events", "all");

        var container = zoomer.append('g')
            .call(zoom)
            .attr('class', 'container');

        var dragConnectorLine = svg.append('path');

        container.append('g').attr('class', 'relation-lines');
        container.append('g').attr('class', 'services');
        container.append('g').attr('class', 'relation-indicators');

        var relation = {};
        var line;
        var indicator;

        d3.selection.prototype.position = function() {
          var el = this.node();
          var elPos = el.getBoundingClientRect();
          var vpPos = getVpPos(el);

          function getVpPos(el) {
            if(el.parentElement.tagName === 'svg') {
              return el.parentElement.getBoundingClientRect();
            }

            return getVpPos(el.parentElement);
          }

          return {
            top: elPos.top - vpPos.top,
            left: elPos.left - vpPos.left,
            width: elPos.width,
            bottom: elPos.bottom - vpPos.top,
            height: elPos.height,
            right: elPos.right - vpPos.left
          };
        };

        // This listens for mouse events on the entire svg element.
        svg.on("dragover", function() {
          mouse = d3.mouse(svg.node());
        }).on("drop", function() {
          save();
        });

        // These are the Angular watch and listeners.
        scope.$on('window:resize', resize);
        scope.$watch('blueprint', function(newVal, oldVal) {
          if(newVal && newVal !== oldVal) {
            var blueprint = {
              nodes: [],
              links: [],
              'meta-data': angular.copy(newVal['meta-data'])
            };
            var _links = {};
            var services = angular.copy(newVal.services);

            for(var service in services) {
              var _entry = services[service];
              _entry._id = service;

              // Map out multiple connections from a service to another service.
              if(_entry.relations) {
                for (i = _entry.relations.length - 1; i >= 0; i--) {
                  for(var component in _entry.relations[i]) {
                    var protocol = _entry.relations[i][component];

                    if(!_links[service]) {
                      _links[service] = {};
                    }

                    if(!_links[service][component]) {
                      _links[service][component] = [];
                    }

                    _links[service][component].push({
                      'protocol': protocol
                    });
                  }
                }
              }

              blueprint.nodes.push(_entry);
            }

            // Push connection map to blueprint.links
            for(var source in _links) {
              for(var target in _links[source]) {
                var _link = {
                  'source': source,
                  'target': target,
                  'connections': _links[source][target]
                };

                blueprint.links.push(_link);
              }
            }

            draw(blueprint);
          }
        }, true);

        // Immediately give a full width/height to svg.
        resize();

        // This draws (or redraws) the blueprint.
        function draw(blueprint) {
          // This resizes and cleans up old container elements.
          container.selectAll('g.service').remove();
          container.selectAll('g.relation-line').remove();
          container.selectAll('g.relation-group').remove();
          dragConnectorLine.remove();
          resize();

          // Append service container
          service = container.select('g.services').selectAll('g.service')
              .data(blueprint.nodes)
            .enter()
            .append('g')
              .attr('class', function(d) {
                var classes = ['service'];
                classes.push(d._id);
                return classes.join(" ");
              })
              .attr('id', function(d) {
                return d._id + '-service';
              })
              .attr("transform", function(d, index) {
                var height = sizes.service.height((d.components || [1]).length);
                var width = sizes.service.width((d.components || [1]).length);
                var coords = {
                  x: ((svg.style('width').replace('px','') * 1) / 2) + (index % 2 ? -1 * 60 : 60) - width,
                  y: ((height + 25) * index) + 25
                };
                var safeMouse = mouse || [coords.x, coords.y]
                var meta = blueprint['meta-data'];

                d.x = ((meta.annotations || {})[d._id] || {})['gui-x'] || safeMouse[0];
                d.y = ((meta.annotations || {})[d._id] || {})['gui-y'] || safeMouse[1];

                return "translate(" + d.x + "," + d.y + ")";
              })
              .on('click', function(d) {
                if(d3.event.defaultPrevented) {
                  return;
                }

                var data = {
                  service: d._id,
                  component: null,
                  relation: null
                };

                //toggleSelect(d3.select(this), data);
                d3.event.stopPropagation();
              });

          // This defines service drag events.
          service.on("dragover", function(d) {
            Drag.target.set(d);
          }).on("dragleave", function(d) {
            Drag.target.set(null);
          }).call(drag);

          // This append the service rectangle container.
          service.append('rect')
            .attr('class', 'service-container')
            .attr("width", function(d) {
              return sizes.service.width((d.components || [1]).length);
            })
            .attr("height", function(d) {
              return sizes.service.height((d.components || [1]).length);
            })
            .attr('rx', sizes.service.radius)
            .attr('ry', sizes.service.radius);

          // This appends the title of service.
          var title = service.append('text')
            .attr('class', 'service-title');

          title.append('title')
            .text(function(d) {
              return d._id;
            });

          title.append('tspan')
            .attr('text-anchor', 'middle')
            .attr('x', function(d) {
              return sizes.service.width((d.components || [1]).length) / 2;
            })
            .attr('y', function(d) {
              return sizes.service.height((d.components || [1]).length) - (sizes.service.margin.bottom / 2) + 3;
            })
            .text(function(d){
              return d._id.toUpperCase();
            });

          // Appends relation lines.
          relation.line = container.select('g.relation-lines')
            .selectAll('g.relation-line')
              .data(blueprint.links)
              .enter()
                .append('g')
                .attr('class', 'relation-line');

          // Appends relation indicators.
          relation.indicator = container.select('g.relation-indicators')
            .selectAll('g.relation-group')
              .data(blueprint.links)
              .enter()
                .append('g')
                .attr('class', 'relation-group');

          line = relation.line.append("line")
            .attr('class', function(d) {
              var classes = ['relation-link'];

              classes.push('source-'+d.source);
              classes.push('target-'+d.target);

              return classes.join(' ');
            })
            .on('mousedown', function() {
              d3.event.stopPropagation();
            });

          connectRelationLines();

          indicator = relation.indicator.append("g")
            .attr('class', function(d) {
              var classes = ['relation-indicator'];
              var status = state['indicator-'+d.source + '-' + d.target];
              var target = d3.select('#'+d.target+'-service');

              if(status && status.active && target[0][0]) {
                classes.push('active');
              }

              return classes.join(' ');
            })
            .attr('id', function(d) {
              return 'indicator-'+d.source + '-' + d.target;
            })
            .on('click', function(d) {
              if(d3.event.defaultPrevented) {
                return;
              }
              d3.event.stopPropagation();

              if(!state['indicator-'+d.source + '-' + d.target]) {
                state['indicator-'+d.source + '-' + d.target] = {
                  active: false
                };
              }

              var status = state['indicator-'+d.source + '-' + d.target];
              var element = d3.select(this);

              element.classed('active', !status.active);
              status.active = !status.active;
            })
            .on('mousedown', function() {
              d3.event.stopPropagation();
            });

          indicator.append('circle')
            .attr('class', 'relation-indicator-circle')
            .attr('r', sizes.indicator.radius);

          indicator.append('path')
            .attr('d', d3.svg.symbol().type('triangle-down'))
            .attr('class', 'connections-arrow')
            .attr('transform', function(d, i) {
              var x = 0;
              var y = -12;
              return 'translate('+x+','+y+')';
            });

          indicator.append('rect')
            .attr('width', sizes.indicator.width)
            .attr('height', function(d, i) {
              return d.connections.length * 24;
            })
            .attr('x', 0)
            .attr('y', 0)
            .attr('transform', function(d, i) {
              var x = -1 * (sizes.indicator.width / 2);
              var y = ((d.connections.length * 24) + sizes.indicator.radius * 2.5) * -1;
              return 'translate('+x+','+y+')';
            })
            .attr('class', 'connections-container');

          var connections = indicator.selectAll('g.connection')
            .data(function(d, i) {
              return d.connections;
            })
            .enter()
              .append('g')
              .attr('class', 'connection')
              .attr('transform', function(d, i) {
                var x = -1 * ((sizes.indicator.width / 2) - sizes.indicator.radius - 1);
                var y = ((i * -1) * sizes.indicator.spacing - 24);

                return 'translate('+x+','+y+')';
              });

          connections.append("text")
            .attr('text-anchor', 'left')
            .attr('class', 'interface-text')
            .html(function(d) {
              var parent = d3.select(this.parentNode.parentNode).datum();
              var protocol = d.protocol.split('#')[0];

              if(d.protocol.split('#')[1]) {
                protocol += ' ('+d.protocol.split('#')[1]+')';
              }

              return parent.source + ' &#8596; ' + parent.target +' : '+protocol;
            });

            connections.append('text')
            .html('&#xf057')
            .attr('x', function(d, index) {
              return sizes.indicator.width - 25;
            })
            .attr('y', function() {
              return 1;
            })
            .attr('class', 'fa fa-times component-remover')
            .on('click', function(d, index) {
              if(d3.event.defaultPrevented) {
                return;
              }
              d3.event.stopPropagation();

              var data = {
                source: d3.select(this.parentNode.parentNode).datum().source,
                target: d3.select(this.parentNode.parentNode).datum().target,
                interface: d.protocol
              };

              removeConnection(data);
            });

          positionIndicatorNodes();

          // This appends components to service container.
          component = service.selectAll('g.component')
              .data(function(d) {
                return d.component ? [d.component] : d.components;
              })
            .enter()
              .append('g')
                .attr('class', 'component')
                .on('click', function(d) {
                  if(d3.event.defaultPrevented) {
                    return;
                  }

                  var data = {
                    service: d3.select(this.parentNode).datum()._id,
                    component: d,
                    relation: null
                  };

                  toggleSelect(d3.select(this), data);
                  d3.event.stopPropagation();
                });

          component.append('rect')
            .attr('width', sizes.component.width())
            .attr('height', sizes.component.height())
            .attr('x', function(d, index) {
              return sizes.service.margin.left + (sizes.component.width() * (index));
            })
            .attr('y', function(d, index) {
              return sizes.service.margin.top;
            })
            .attr('class', 'component-container');

          component.append('text')
            .html('&#xf057')
            .attr('x', function(d, index) {
              return sizes.service.margin.left + (sizes.component.width() * (index + 1)) - 16;
            })
            .attr('y', function() {
              return 25;
            })
            .attr('class', 'fa fa-times component-remover')
            .on('click', function(d, index) {
              if(d3.event.defaultPrevented) {
                return;
              }
              d3.event.stopPropagation();

              var data = {
                service: d3.select(this.parentNode.parentNode).datum()._id,
                component: d.id || d.name,
                index: index
              };

              removeComponent(data);
            });

          component.append('image')
            .attr('fill', 'black')
            .attr('width', sizes.component.width() - 64)
            .attr('height', sizes.component.height() - 64)
            .attr('transform', function(d, index) {
              var x = sizes.service.margin.left + (sizes.component.width() * (index)) + 32;
              var y = sizes.service.margin.top + 40;

              return 'translate('+x+','+y+')';
            })
            .attr('xlink:href', function(d) {
              return scope.getTattoo((d.name || d.id));
            })
            .attr('class', 'component-icon');

          // This adds a component label.
          var label = component.append('text')
            .attr('class', 'component-title');

          label.append('title')
            .text(function(d) {
              return getDisplayName(d);
            });

          label.append('tspan')
            .attr('text-anchor', 'middle')
            .attr('x', function(d, index) {
              var x = sizes.service.margin.left + (sizes.component.width() / 2);

              if(index > 0) {
                x = x + (sizes.component.width() * index);
              }

              return x;
            })
            .attr('y', function(d) {
              return sizes.service.margin.top + 28;
            })
            .text(function(d) {
              var label = getDisplayName(d);

              if(label.length > 12) {
                label = label.substring(0,11) + '...';
              }

              return label;
            });

          // This draws the linker thingy
          var linker = component.append('g')
            .style("pointer-events", "all")
            .attr('class', 'relation-linker')
            .on('click', function(d) {
              if(d3.event.defaultPrevented) {
                return;
              }

              var data = {
                service: d3.select(this.parentNode).datum()._id,
                component: d,
                relation: null
              };

              toggleSelect(d3.select(this), data);
              d3.event.stopPropagation();
            })
            .call(linkerDrag);

          linker.append('circle')
            .attr('r', 12)
            .attr('fill', '#f6f6f6')
            .attr('cx', function(d, index) {
              return sizes.service.margin.left + (sizes.component.width() * (index + 1)) - 18;
            })
            .attr('cy', function(d, index) {
              return sizes.component.height() - 7;
            })
            .attr('class', 'relation-link-container');

          linker.append('text')
            .style("pointer-events", "none")
            .html('&#xf0c1')
            .attr('x', function(d, index) {
              return sizes.service.margin.left + (sizes.component.width() * (index + 1)) - 24;
            })
            .attr('y', function(d, index) {
              return sizes.component.height() - 2;
            })
            .attr('class', 'fa fa-link relation-linker-icon');

          // TODO: This is a backup for drag events not firing due to propagation issues.
          component.style("pointer-events", "all")
            .on("mouseover", function(d) {
              if (state.linking) {
                var source = Drag.source.get();
                var target = {
                  componentId: d.id || d.name,
                  serviceId: d3.select(this.parentNode).datum()._id,
                  interface: null
                };

                if (source.serviceId === target.serviceId && source.componentId === target.componentId) {
                  return;
                }

                if (Blueprint.canConnect(source, target)) {
                  d3.select(this).classed('unsuitable', false);
                } else {
                  d3.select(this).classed('unsuitable', true);
                }

                Drag.target.set(target);

                d3.select(this).classed('target', true);
              }
            }).on("mouseout", function(d) {
              if (state.linking) {
                d3.select(this).classed('target unsuitable', false);
                Drag.target.set(null);
              }
            }).on("mouseup", function(d) {
              if (state.linking) {
                var target = Drag.target.get();
                var source = Drag.source.get();
                var connections = Blueprint.canConnect(source, target);
                var components = Catalog.getComponents();

                // Add interface
                if(connections.length == 1) {
                  target.interface = connections[0].interface;

                  if(target && target.interface) {
                    scope.connect();
                  }
                } else if(connections.length > 1) {
                  // Ask user to select connection instead.
                  determineProtocol(d3.select(this), connections);
                }

                d3.select(this).classed('target unsuitable', false);
              }
            });
        }

        function determineProtocol(element, connections) {
          // Spawns popover asking for user input
          var selector = element.append('g')
            .attr('class', 'interface-selector')
            .attr('transform', "translate(" + sizes.component.width() + "," + sizes.component.height() + ")")

          selector.append('rect')
            .attr('class', 'interface-container')
            .attr('height', function() {
              return connections.length * 25;
            })
            .attr('width', sizes.interfaces.width())
            .attr('x', 0)
            .attr('y', 0);

          var options = selector.selectAll('g.interface-selector')
              .data(connections)
            .enter()
            .append('g')
            .attr('class', 'interface-option')
            .on('mousedown', function(d) {
              d3.event.stopPropagation();
            }).on('click', function(d) {
              if(d3.event.defaultPrevented) {
                return;
              }
              d3.event.stopPropagation();
              setProtocol(d.interface, d.type);
            });

          options.append('rect')
            .attr('x', 0)
            .attr('y', function(d, index) {
              return index * sizes.interfaces.height()
            })
            .attr('width', sizes.interfaces.width())
            .attr('height', sizes.interfaces.height());

          var option = options.append('text')
            .attr('class', 'interface-title');

          option.append('title')
            .text(function(d) {
              return d.type + ' ' + d.interface.substring(0,12);
            });

          option.append('tspan')
            .attr('text-anchor', 'left')
            .attr('x', function(d) {
              return 10;
            })
            .attr('y', function(d, index) {
              return ((sizes.interfaces.height() - 2) * (index + 1)) - 5;
            })
            .text(function(d) {
              var text = '';

              if(d.type) {
                text = d.type;
              } else {
                text = d.interface;
              }

              if(text.length > 12) {
                text = text.substring(0,12);
                text += '...';
              }

              return text;
            });
        }

        function setProtocol(interface, connectFrom) {
          var target = Drag.target.get();
          target.interface = interface;
          target['connect-from'] = connectFrom;
          Drag.target.set(target);

          scope.connect();
        }

        function toggleSelect(el, data) {
          if (el.classed('selected')) {
            el.classed('selected', false);
            scope.deselect(data);
          } else {
            svg.selectAll('.selected').classed('selected', false);
            el.classed('selected', true);
            scope.select(data);
          }
        }

        function removeComponent(data) {
          scope.remove(data);
        }

        function removeConnection(data) {
          scope.sever(data);
        }

        function getCoords(element) {
          var position = {
            x: 0,
            y: 0
          };
          var size;

          if(!element[0][0]) {
            return position;
          }

          size = element.node().getBBox();

          position.x = element.datum().x;
          position.y = element.datum().y;

          return {
            x: position.x + (size.width / 2),
            y: position.y + (size.height / 2)
          }
        }

        function linkstarted(d) {
          state.linking = true;
          var coords = getCoords(d3.select(this.parentNode.parentNode));

          dragConnectorLine = svg
            .append('path')
            .attr('class', 'linker dragline')
            .style("pointer-events", "none")
            .attr('d', 'M0,0L0,0');

          Drag.reset();
          Drag.source.set({
            componentId: d.id || d.name,
            serviceId: d3.select(this.parentNode.parentNode).datum()._id
          });
          d3.event.sourceEvent.stopPropagation();
          d3.select(this).classed("dragging dragged", true);
        }

        function linkdragged(d) {
          var source = Drag.source.get();
          var target = null;
          var elem = d3.select(this);
          var box = elem.position();  // TODO: account for zoom
          var mouse = d3.mouse(zoomer[0][0]);

          component.classed('deactivated', function(d) {
            target = {
              componentId: d.id || d.name,
              serviceId: d3.select(this.parentNode).datum()._id
            };

            if (source && target) {
              if (!Blueprint.canConnect(source, target)) {
                return true;
              }
            }
          });

          dragConnectorLine.attr('d', 'M' + (box.left + box.width/2) + ',' + (box.top + box.height/2) + 'L' + mouse[0] + ',' + mouse[1]);
        }

        function linkended(d) {
          //Drag.reset();
          d3.event.sourceEvent.stopPropagation();
          d3.select(this).classed("dragging", false);
          component.classed('deactivated', false);
          state.linking = false;
          dragConnectorLine.remove();
        }

        function getDisplayName(d) {
          var display = Catalog.getComponent(d.id || d.name).display_name;
          var label =  display || d.id || d.name;

          return label;
        }

        function resize() {
          svg.attr('width', parent.clientWidth);
          svg.attr('height', parent.clientHeight);

          rect.attr('width', parent.clientWidth);
          rect.attr('height', parent.clientHeight);
        }

        function zoomed() {
          state.translation = d3.event.translate;
          state.scale = d3.event.scale;
          dragConnectorLine.remove();
          container.attr("transform", "translate(" + d3.event.translate + ")scale(" + d3.event.scale + ")");
        }

        function dragstarted(d) {
          d3.event.sourceEvent.stopPropagation();
          d3.select(this).classed("dragging dragged", true);
        }

        function dragged(d) {
          d.x = d3.event.x;
          d.y = d3.event.y;

          d3.select(this).attr("transform", "translate(" + d.x + "," + d.y + ")");

          connectRelationLines();
          positionIndicatorNodes();
        }

        function positionIndicatorNodes() {
          indicator.attr("transform", function(d) {
            var source = d3.select('#'+d.source+'-service');
            var target = d3.select('#'+d.target+'-service');
            var x = 0;
            var y = 0;

            if(!target[0][0]) {
              target = source;
            }

            x = (getCoords(source).x + getCoords(target).x) / 2;
            y = (getCoords(source).y + getCoords(target).y) / 2;

            return 'translate('+x+','+y+')';
          });
        }

        function connectRelationLines() {
          line.attr("x1", function(d) {
              var ele = d3.select('#'+d.source+'-service');
              return getCoords(ele).x;
            })
            .attr("y1", function(d) {
              var ele = d3.select('#'+d.source+'-service');
              return getCoords(ele).y;
            })
            .attr("x2", function(d) {
              var ele = d3.select('#'+d.target+'-service');
              if(!ele[0][0]) {
                return d3.select(this).attr('x1');
              }
              return getCoords(ele).x;
            })
            .attr("y2", function(d) {
              var ele = d3.select('#'+d.target+'-service');
              if(!ele[0][0]) {
                return d3.select(this).attr('y1');
              }
              return getCoords(ele).y;
            });
        }

        function dragended(d) {
          d3.event.sourceEvent.stopPropagation();
          d3.select(this).classed("dragging", false);
          save();
          Drag.reset();
        }

        function save() {
          var services = d3.selectAll("g.service");
          var blueprint = {
            services: {},
            'meta-data': {
              annotations: {}
            }
          };

          // This loops over the svg's services and converts it to an object.
          services.each(function(d) {
            var _service = angular.copy(d);
            var annotations;

            // This removes svg-related properties.
            delete _service._id;
            delete _service.x;
            delete _service.y;

            // This handles the meta-data annotations.
            if(!blueprint['meta-data'].annotations[d._id]) {
              blueprint['meta-data'].annotations[d._id] = {};
            }

            annotations = blueprint['meta-data'].annotations[d._id];

            annotations['gui-x'] = Number((d.x || 100).toFixed(3));
            annotations['gui-y'] = Number((d.y || 100).toFixed(3));

            // This extends any current
            blueprint.services[d._id] = blueprint.services[d._id] || {};
            _.extend(blueprint.services[d._id], _service);
          });

          // Only overwrite services and meta-data
          var original = Blueprint.get();

          original.services = blueprint.services;
          _.extend(original['meta-data'], blueprint['meta-data']);

          Blueprint.set(original);
        }
      }
    };
  });
