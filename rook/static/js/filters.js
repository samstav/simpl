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
    if (d === 0) {
      return "now";
    } else
      return d ? moment().add('seconds', d).fromNow() : '';
  };
});

filters.filter('prepend', function() {
  return function(d, p) {
    if (d)
      return (p || "/") + d;
    return '';
  };
});

filters.filter('yaml', function() {
  return function(d) {
    return d ? YAML.stringify(d) : '';
  };
});

filters.filter('snippet', function() {
  return function(d, chars) {
    if (d) {
      if (d.length > (chars || 2000)) {
        return d.substr(0, chars || 2000) + '...';
      } else {
        return d;
      }
    }
    return '';
  };
});

filters.filter('checkmark', function() {
  return function(input) {
    return input ? '\u2713' : '\u2718';
  };
});


filters.filter('truncate', function() {
    return function(input, max_length) {
      if (input === null || input === "") {
        return "...[no name]...";
      }

      if (input.length > max_length) {
        return input.substring(0, (max_length-3)) + '...';
      } else {
        return input;
      }
    };
  });

filters.filter('idIn', function() {
  return function(d, array) {
    if (d) {
        return _.filter(d, function(item){return (array.indexOf(item.id) != -1);});
    }
  };
});

filters.filter('idNotIn', function() {
  return function(d, array) {
    if (d) {
        return _.filter(d, function(item){return (array.indexOf(item.id) == -1);});
    }
  };
});

filters.filter('capitalize',
  function() {
    return function(input) {
      if(angular.isString(input) && input.length){
        return input.charAt(0).toUpperCase() + input.slice(1);
      }
      return input;
    };
  }
);

filters.filter('cm_validation_rules', function() {
  return function(constraints) {
    var html = "<div class='validation_rules'>";
    if (constraints) {
      for (var idx=0 ; idx<constraints.length ; idx++)
      {
        var icon = constraints[idx].valid ? 'icon-ok' : 'icon-remove';
        html += '<i class="'+ icon +'"></i>';
        html += '<span class="message">' + (constraints[idx].message || "") + '</span>';
        html += '<br>';
      }
    }
    html += "</div>";

    return html;
  };
});
