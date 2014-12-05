angular.module('checkmate.Blueprint')
  .directive('blueprintTopology', function($window, Drag, Blueprint, $timeout, Catalog) {
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

        var sizes = {
          component: {
            width: function() {
              return 160;
            },
            height: function() {
              return 160;
            },
            margin: {
              top: 10,
              right: 10,
              bottom: 10,
              left: 10
            }
          },
          service: {
            height: function(components) {
              var rows = Math.ceil(components / sizes.service.rows);
              var height = (sizes.component.height() * rows);
              height = height + sizes.service.margin.top + sizes.service.margin.bottom;

              return height;
            },
            width: function(components) {
              var columns = components;

              if(components > sizes.service.columns) {
                columns = Math.ceil(components / sizes.service.columns);
              }

              var width = (sizes.component.width() * columns);
              width = width + sizes.service.margin.left + sizes.service.margin.right;

              return width;
            },
            columns: 4,
            rows: 4,
            margin: {
              top: 10,
              right: 10,
              bottom: 40,
              left: 10
            },
            radius: 10
          }
        };

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

        var zoomer = svg.append("g")
            .attr("transform", "translate(0,0)")
            .call(zoom)
            .attr('class', 'zoomer')
            .on('click', function(d) {
              if(d3.event.defaultPrevented) {
                return;
              }
              console.log("CANVAS");
              toggleSelect(d3.select(this), null);
            });

        var rect = zoomer.append("rect")
            .style("fill", "none")
            .style("pointer-events", "all");

        var container = zoomer.append("g")
            .call(zoom)
            .attr('class', 'container');

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
            var blueprint = [];
            var services = angular.copy(newVal.services);

            for(var key in services) {
              var _entry = services[key];
              _entry._id = key;
              blueprint.push(_entry);
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
              .data(blueprint)
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
                var annotations = d.annotations || {};
                var safeMouse = mouse || [100, 100];
                d.x = annotations['gui-x'] || safeMouse[0];
                d.y = annotations['gui-y'] || safeMouse[1];

                return "translate(" + d.x + "," + d.y + ")";
              })
              .on('click', function(d) {
                if(d3.event.defaultPrevented) {
                  return;
                }
                console.log('SERVICE', d._id);

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

          // This appends components to service container.
          component = service.selectAll('g.component')
              .data(function(d) {
                return d.components;
              })
            .enter()
              .append("g")
                .attr('class', 'component')
                .on('click', function(d) {
                  if(d3.event.defaultPrevented) {
                    return;
                  }
                  console.log('COMPONENT', d);

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

          component.append('image')
            .attr('fill', 'black')
            .attr('width', sizes.component.width() - 50)
            .attr('height', sizes.component.height() - 50)
            .attr('transform', function(d, index) {
              var x = sizes.service.margin.left + (sizes.component.width() * (index)) + 25;
              var y = sizes.service.margin.top + 37;

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
              return sizes.service.margin.top + 25;
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
              console.log('LINKER', d);

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
            .attr('class', 'fa-link relation-linker-icon');

          // This defines linker drag events.
          linker.on("dragenter", function(d) {
            console.log("enter");
            d3.select(this).classed('target', true);
            Drag.target.set({componentId: d, serviceId: d3.select(this.parentNode.parentNode).datum()._id});
          }).on("dragover", function(d) {
            console.log("OVER");
          }).on("dragleave", function(d) {
            Drag.target.set(null);
            d3.select(this).classed('target unsuitable', false);
            console.log("LEAVE");
          }).on("drop", function() {
            console.log("DROP");
            d3.select(this).classed('target unsuitable', false);
          });

          // TODO: This is a backup for drag events not firing
          linker.on("mouseover", function(d) {
            if (state.linking) {
              var source = Drag.source.get();
              var target = {componentId: d, serviceId: d3.select(this.parentNode.parentNode).datum()._id};
              if (source.serviceId === target.serviceId && source.componentId === target.componentId) {
                console.log("SELF");
                return;
              } else {
                console.log("OTHER", source, target);
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
            console.log("OUT", d);
            if (state.linking) {
              d3.select(this).classed('target unsuitable', false);
              Drag.target.set(null);
            }
          }).on("mouseup", function(d) {
            console.log("UP", d);
            if (state.linking) {
              d3.select(this).classed('target unsuitable', false);
            }
          });

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
          var elem = d3.select(this);
          var box = elem.position();  // TODO: account for zoom
          var mouse = d3.mouse(zoomer[0][0]);
          dragConnectorLine.attr('d', 'M' + (box.left + box.width/2) + ',' + (box.top + box.height/2) + 'L' + mouse[0] + ',' + mouse[1]);
        }

        function linkended(d) {
          state.linking = false;
          dragConnectorLine.remove();
          d3.event.sourceEvent.stopPropagation();
          d3.select(this).classed("dragging", false);
          var target = Drag.target.get();
          if (target) {
            console.log("DROP", target);
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
        }

        function dragended(d) {
          d3.event.sourceEvent.stopPropagation();
          d3.select(this).classed("dragging", false);
          save();
          Drag.reset();
        }

        function save() {
          var services = d3.selectAll("g.service");
          //var relations = d3.selectAll("g.relation");
          var blueprint = {
            services: {}
          };

          // This loops over the svg's services and converts it to an object.
          services.each(function(d) {
            var _service = angular.copy(d);

            // This removes svg-related properties.
            delete _service._id;
            delete _service.x;
            delete _service.y;

            // This adds annotations property.
            _service.annotations = {
              'gui-x': Number((d.x || 100).toFixed(3)),
              'gui-y': Number((d.y || 100).toFixed(3))
            };

            // This extends any current
            blueprint.services[d._id] = blueprint.services[d._id] || {};
            _.extend(blueprint.services[d._id], _service);
          });

          // Only overwrite services
          var original = Blueprint.get();
          original.services = blueprint.services;
          Blueprint.set(original);
        }
      }
    };
  });
