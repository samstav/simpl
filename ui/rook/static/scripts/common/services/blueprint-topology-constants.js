angular.module('checkmate.Blueprint')
  .factory('Sizes', function() {
    var sizes = {
      component: {
        width: function() {
          return 120;
        },
        height: function() {
          return 120;
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
      },
      indicator: {
        radius: 6,
        width: 240,
        spacing: 23
      },
      interfaces: {
        height: function() {
          return 25;
        },
        width: function() {
          return 80;
        }
      }
    };

    return sizes;
  });
