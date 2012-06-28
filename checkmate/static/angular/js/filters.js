angular.module('checkmateFilters', [])
  .filter('checkmark', function() {           //this is an example
    return function(input) {
      return input ? '\u2713' : '\u2718';
    }
  })
  .filter('truncate', function() {
    return function(input, max_length) {
      if (input == null || input == "") {
        return "...[no name]...";
      }

      if (input.length > max_length) {
        return input.substring(0, (max_length-3)) + '...';
      } else {
        return input;
      }
    }
  });