var module = angular.module("lvl.directives.dragdrop", ['lvl.services']);

module.directive('lvlDraggable', ['$rootScope', 'uuid',
  function($rootScope, uuid) {
    return {
      restrict: 'A',
      link: function(scope, el, attrs, controller) {
        angular.element(el).attr("draggable", "true");

        el.bind("dragstart", function(e) {
          $rootScope.$emit("LVL-DRAG-START");
        });

        el.bind("dragend", function(e) {
          $rootScope.$emit("LVL-DRAG-END");
        });
      }
    }
  }]);

module.directive('lvlDropTarget', ['$rootScope', 'uuid',
  function($rootScope, uuid) {
    return {
      restrict: 'A',
      scope: {
        onDrop: '&'
      },
      link: function(scope, el, attrs, controller) {
        el.bind("dragover", function(e) {
          if (e.preventDefault) {
            e.preventDefault(); // Necessary. Allows us to drop.
          }

          e.originalEvent.dataTransfer.dropEffect = 'copy';
          return false;
        });

        el.bind("dragenter", function(e) {
          angular.element(e.target).addClass('lvl-over');
        });

        el.bind("dragleave", function(e) {
          angular.element(e.target).removeClass('lvl-over');
        });

        el.bind("drop", function(e) {
          if (e.preventDefault) {
            e.preventDefault();
          }

          if (e.stopPropagation) {
            e.stopPropagation();
          }

          scope.onDrop();
        });

        $rootScope.$on("LVL-DRAG-START", function() {
          el.addClass("lvl-target");
        });

        $rootScope.$on("LVL-DRAG-END", function() {
          el.removeClass("lvl-target");
          el.removeClass("lvl-over");
        });
      }
    }
  }]);
