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

        var dragConnectorLine = null;
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

        container.append('g').attr('class', 'relations');

        var relation;
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
          container.selectAll('g.relation').remove();
          resize();

          // Append service container
          service = container.selectAll('g.service')
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
              .attr("transform", function(d) {
                var safeMouse = mouse || [100, 100];
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

                toggleSelect(d3.select(this), data);
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
              return sizes.service.width(d.components.length);
            })
            .attr("height", function(d) {
              return sizes.service.height(d.components.length);
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
              return sizes.service.width(d.components.length) / 2;
            })
            .attr('y', function(d) {
              return sizes.service.height(d.components.length) - (sizes.service.margin.bottom / 2) + 3;
            })
            .text(function(d){
              return d._id.toUpperCase();
            });

          // Appends relation lines.
          relation = container.select('g.relations')
            .selectAll('g.relation')
              .data(blueprint.links)
              .enter()
                .append('g')
                .attr('class', 'relation');

          line = relation.append("line")
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

          indicator = relation.append("g")
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
              return 25;
            })
            .attr('x', 0)
            .attr('y', 0)
            .attr('transform', function(d, i) {
              var x = -1 * (sizes.indicator.width / 2);
              var y = (sizes.indicator.spacing + ((sizes.indicator.radius + 2) * 2)) * -1;
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
                return 'translate(0,'+((i-1)*sizes.indicator.spacing)+')'; // ext sizes
              });

          connections.append("text")
            .attr('text-anchor', 'middle')
            .text(function(d) {
              var parent = d3.select(this.parentNode.parentNode).datum();
              return parent.source +':'+d.protocol+' - '+parent.target +':'+d.protocol;
            });

          positionIndicatorNodes();

          // This appends components to service container.
          component = service.selectAll('g.component')
              .data(function(d) {
                return d.components;
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
            .attr('y', function(d, index) {
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
                component: d,
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
              return scope.getTattoo(d);
            })
            .attr('class', 'component-icon');

          // This adds a component label.
          var label = component.append('text')
            .attr('class', 'component-title');

          label.append('title')
            .text(function(d) {
              return d;
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
              var label = d;

              if(d.length > 12) {
                label = label.slice(0,9) + '...';
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

          // This defines linker drag events.
          linker.on("dragenter", function(d) {
            d3.select(this).classed('target', true);
            Drag.target.set({componentId: d, serviceId: d3.select(this.parentNode.parentNode).datum()._id});
          }).on("dragover", function(d) {
          }).on("dragleave", function(d) {
            Drag.target.set(null);
            d3.select(this).classed('target unsuitable', false);
          }).on("drop", function() {
            d3.select(this).classed('target unsuitable', false);
          });

          // TODO: This is a backup for drag events not firing
          linker.on("mouseover", function(d) {
            if (state.linking) {
              var source = Drag.source.get();
              var target = {
                componentId: d,
                serviceId: d3.select(this.parentNode.parentNode).datum()._id,
                protocol: d
              };

              if (source.serviceId === target.serviceId && source.componentId === target.componentId) {
                return;
              }

              d3.select(this).classed('target', true);

              if (Blueprint.canConnect(source, target)) {
                Drag.target.set(target);
                d3.select(this).classed('unsuitable', false);
              } else {
                d3.select(this).classed('unsuitable', true);
              }
            }
          }).on("mouseout", function(d) {
            if (state.linking) {
              d3.select(this).classed('target unsuitable', false);
              Drag.target.set(null);
            }
          }).on("mouseup", function(d) {
            if (state.linking) {
              d3.select(this).classed('target unsuitable', false);
            }
          });
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
          dragConnectorLine = svg.append('path')
              .style("pointer-events", "none")
              .attr('class', 'linker dragline')
              .attr('d', 'M0,0L0,0');
          Drag.source.set({componentId: d, serviceId: d3.select(this.parentNode.parentNode).datum()._id});
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
            target = {componentId: d, serviceId: d3.select(this.parentNode).datum()._id};

            if (source && target) {
              if (!Blueprint.canConnect(source, target)) {
                return true;
              }
            }
          });

          dragConnectorLine.attr('d', 'M' + (box.left + box.width/2) + ',' + (box.top + box.height/2) + 'L' + mouse[0] + ',' + mouse[1]);
        }

        function linkended(d) {
          state.linking = false;
          dragConnectorLine.remove();
          d3.event.sourceEvent.stopPropagation();
          d3.select(this).classed("dragging", false);
          component.classed('deactivated', false);
          var source = Drag.source.get();
          var target = Drag.target.get();
          if (source && target) {
            if (Blueprint.canConnect(source, target)) {
              Blueprint.connect(source.serviceId, target.serviceId, target.protocol);
            }
          }
          Drag.reset();
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
