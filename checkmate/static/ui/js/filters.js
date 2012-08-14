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