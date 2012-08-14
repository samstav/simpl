var filters = angular.module('checkmateFilters', []);

filters.filter('checkmark', function() {           //this is an example
    return function(input) {
      return input ? '\u2713' : '\u2718';
    }
  });

filters.filter('truncate', function() {
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

filters.filter('formattedDate', function() {
  return function(d) {
    return d ? moment(d).fromNow() : '';
  };
});


filters.filter('formattedFullDate', function() {
  return function(d) {
    return d ? moment(d).format('MMMM Do YYYY, h:mm a') : '';
  };
});
