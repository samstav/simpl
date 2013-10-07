module.exports = function(config) {
  config.set({
    basePath: '../',
    frameworks: ['jasmine'],
    browsers: ['PhantomJS'],
    files: [
      'libs/modernizr-2.5.3.min.js',
      'libs/codemirror-3.18/lib/codemirror.js',
      'libs/codemirror-3.18/mode/javascript/javascript.js',
      'libs/codemirror-3.18/addon/fold/foldcode.js',
      'libs/codemirror-3.18/addon/fold/brace-fold.js',
      'libs/codemirror-3.18/addon/hint/javascript-hint.js',
      'libs/codemirror-3.18/addon/hint/show-hint.js',
      'libs/jquery-1.7.2.min.js',
      'libs/bootstrap-2.3.1/js/bootstrap.min.js',
      'libs/underscore-min.js',
      'libs/yaml.js',
      'libs/moment.min.js',
      'libs/jquery.timeago.js',
      'libs/google-code-prettify-rev187/prettify.js',
      'libs/jquery.jsPlumb-1.3.10-all-min.js',
      'libs/d3.v2.min.js',
      'libs/bootstrap-notify/js/bootstrap-notify.js',
      'libs/jquery.validation-1.10.0/jquery.validate.min.js',
      'libs/jquery.validation-1.10.0/additional-methods.min.js',
      'libs/URI-1.10.2.js',
      'libs/strapdown-0.2/marked.min.js',
      'libs/angular-1.2.0-rc.2/angular.js',
      'libs/angular-1.2.0-rc.2/angular-cookies.js',
      'libs/angular-1.2.0-rc.2/angular-resource.js',
      'libs/angular-1.2.0-rc.2/angular-sanitize.js',
      'libs/angular-1.2.0-rc.2/angular-mocks.js',
      'libs/angular-ui-0.4.0/js/angular-ui.min.js',
      'libs/angular-ui-0.4.0/js/angular-ui-ieshiv.min.js',
      'libs/ui-bootstrap-0.2.0/ui-bootstrap-0.2.0.min.js',
      'libs/ui-bootstrap-0.2.0/ui-bootstrap-tpls-0.2.0.min.js',
      'js/*.js',
      'test/libs/sinon-1.7.1.js',
      'test/libs/jasmine-sinon.js',
      'test/**/*.js'
    ],
    junitReporter: {
      outputFile: 'test-results.xml'
    },
    exclude: [
      'js/background.js'
    ],
    logLevel: config.LOG_ERROR,
    logColors: true,
    autoWatch: true,
    autoWatchInterval: 1
  });
}

