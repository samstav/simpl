var filters = angular.module('checkmate.filters', []);


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

filters.filter('secondsETA', function() {
  return function(d) {
    if (d == 0) {
      return "now";
    } else
      return d ? moment().add('seconds', d).fromNow() : '';
  };
});

filters.filter('prepend', function() {
  return function(d) {
    if (d)
      return "/" + d;
  };
});

filters.filter('yaml', function() {
  return function(d) {
    return d ? YAML.encode(d) : '';
  };
});

filters.filter('snippet', function() {
  return function(d) {
    return d ? d.substr(0, 2000) + '...' : '';
  };
});

filters.filter('checkmark', function() {
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
