angular.module('checkmate.Drag', []);
angular.module('checkmate.Drag')
  .factory('Drag', function() {
    return {
      reset: function() {
        this.target.data = null;
        this.current.data = null;
      },
      target: {
        data: null,
        get: function() {
          return this.data;
        },
        set: function(data) {
          this.data = data;
        }
      },
      current: {
        data: null,
        get: function() {
          return this.data;
        },
        set: function(data) {
          this.data = data;
        }
      },
      source: {
        data: null,
        get: function() {
          return this.data;
        },
        set: function(data) {
          this.data = data;
        }
      }
    };
  });