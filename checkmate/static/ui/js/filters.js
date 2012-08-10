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