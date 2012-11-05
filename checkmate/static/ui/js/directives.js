var directives = angular.module('checkmate.directives', []);

directives.directive('wUp', function() {
  return function(scope, elm, attr) {
    elm.bind('keydown', function(e) {
      switch (e.keyCode) {
        case 34: // PgDn
        case 39: // right arrow
        case 40: // down arrow
        case 74: // j
          return scope.$apply(attr.wDown);

        case 32: // Space
        case 33: // PgUp
        case 37: // left arrow
        case 38: // up arrow
        case 75: // k
          return scope.$apply(attr.wUp);

        case 85: // U
          return scope.$apply(attr.wRead);

        case 72: // H
          return scope.$apply(attr.wStar);
      }
    });
  };
});

directives.directive('compileHtml', function($compile) {
  return {
    restrict: 'A',
    scope: {
      compileHtml: '='
    },
    replace: true,

    link: function(scope, element, attrs) {
      scope.$watch('compileHtml', function(value) {
        element.html($compile(value)(scope.$parent));
      });
    }
  };
});

directives.directive('calculator', function factory() {
  var calculator = {
    templateUrl: '/static/RackspaceCalculator/index.html',
    replace: false,
    transclude: false,
    restrict: 'E',
    scope: false,
    compile: function compile(tElement, tAttrs, transclude) {
      return {
        post: function postLink(scope, iElement, iAttrs, controller) {
          //Remove unneeded stuff
          $("#basement-wrap").remove();
          $("#footer-wrap").remove();
          $("#ceiling-wrap").remove();
          $("#banner-v2-wrap").remove();
          $('calculator').children('link').remove();
          $('calculator').children('title').remove();

          $('head').append('<link rel="stylesheet" href="/static/RackspaceCalculator/css/rackspace.min.css">');
          $('head').append('<link rel="stylesheet" href="/static/RackspaceCalculator/css/styles.css">');
          $("#page-wrap").insertBefore('.mainContent');
          $("#content-wrap").css("top", "40px"); //.insertBefore('.mainContent');
          $(".mainContent").css("display", "none");
          $("body").addClass("chrome");
          $(".signup").text("Build It");
          $('head').append('<script src="/static/RackspaceCalculator/js/jquery-ui-1.8.21.min.js"></script>');
          $('head').append('<script src="/static/RackspaceCalculator/js/lodash.js"></script>');
          $('head').append('<script src="/static/RackspaceCalculator/js/json2.js"></script>');
          $('head').append('<script src="/static/RackspaceCalculator/js/backbone.js"></script>');
          $('head').append('<script src="/static/RackspaceCalculator/js/backbone-localstorage.js"></script>');
          $('head').append('<script src="/static/RackspaceCalculator/js/backbone.subset.js"></script>');
          $('head').append('<script src="/static/RackspaceCalculator/js/calcapp.js"></script>');
        }
      }
    }
  };
  return calculator;
});

directives.directive('compat', function factory($scope) {
  var tenantId = $scope.auth.tenantId;
  var compat = {
    templateUrl: '/' + tenantId + '/workflows/simulate.html',
    replace: false,
    transclude: false,
    restrict: 'E',
    scope: false,
    compile: function compile(tElement, tAttrs, transclude) {
      return {
        post: function postLink(scope, iElement, iAttrs, controller) {
          $(".container-fluid").insertBefore('.mainContent');
          $('compat .navbar').remove();
          return;
          //Remove unneeded stuff
          $("#basement-wrap").remove();
          $("#footer-wrap").remove();
          $("#ceiling-wrap").remove();
          $("#banner-v2-wrap").remove();
          $('calculator').children('link').remove();
          $('calculator').children('title').remove();

          $('head').append('<link rel="stylesheet" href="/static/RackspaceCalculator/css/rackspace.min.css">');
          $('head').append('<link rel="stylesheet" href="/static/RackspaceCalculator/css/styles.css">');
          $("#content-wrap").css("top", "40px"); //.insertBefore('.mainContent');
          $(".mainContent").css("display", "none");
          $("body").addClass("chrome");
          $(".signup").text("Built It");
          $('head').append('<script src="/static/RackspaceCalculator/js/jquery-ui-1.8.21.min.js"></script>');
          $('head').append('<script src="/static/RackspaceCalculator/js/lodash.js"></script>');
          $('head').append('<script src="/static/RackspaceCalculator/js/json2.js"></script>');
          $('head').append('<script src="/static/RackspaceCalculator/js/backbone.js"></script>');
          $('head').append('<script src="/static/RackspaceCalculator/js/backbone-localstorage.js"></script>');
          $('head').append('<script src="/static/RackspaceCalculator/js/backbone.subset.js"></script>');
          $('head').append('<script src="/static/RackspaceCalculator/js/calcapp.js"></script>');
        }
      }
    }
  };
  return compat;
});

directives.directive('clippy', function factory() {
  var directiveDefinitionObject = {
    priority: 0,
    template: '<span></span>',
    controller: function($scope) {
        $scope.encode = function(data) {
            return encodeURIComponent(data);
            }
    },
    replace: true,
    transclude: false,
    restrict: 'E',
    scope: {content: '@content', swf: '@swf', bgcolor: '@bgcolor'},
    compile: function(tElement, tAttrs, transclude) {
        return {
            post: function(scope, elm, attrs, ctrl) {
                // observe changes to interpolated attribute and only add sources when we have data
                attrs.$observe('content', function(value) {
                  if (value) {
                    var clippy_html = '<object classid="clsid:d27cdb6e-ae6d-11cf-96b8-444553540000"\
                                width="110"\
                                height="14"\
                                id="clippy" >\
                        <param name="allowScriptAccess" value="always" />\
                        <param name="quality" value="high" />\
                        <param name="scale" value="noscale" />\
                        <param name="movie" value="' + (scope.swf || "/static/libs/clippy/clippy.swf") + '">\
                        <param NAME="FlashVars" value="text=' + encodeURIComponent(scope.content) + '">\
                        <embed src="' + (scope.swf || "/static/libs/clippy/clippy.swf") + '"\
                               width="110"\
                               height="14"\
                               name="clippy"\
                               quality="high"\
                               allowScriptAccess="always"\
                               type="application/x-shockwave-flash"\
                               pluginspage="http://www.macromedia.com/go/getflashplayer"\
                               FlashVars="text=' + encodeURIComponent(scope.content) + '"\
                               bgcolor="' + scope.bgcolor +'"\
                        />\
                        </object>'
                    elm.children('object').remove();
                    elm.append(clippy_html);
                  }
                });
            }
        }
    }
  };
  return directiveDefinitionObject;
});
