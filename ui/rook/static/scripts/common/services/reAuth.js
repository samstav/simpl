angular.module('checkmate.reAuth', []);

angular.module('checkmate.reAuth')
  .factory('authHttpResponseInterceptor',['$q', '$location', '$rootScope', function($q, $location, $rootScope) {
    'use strict';

    return {
      responseError: function(rejection) {
        if (rejection.status === 401 && rejection.config.url !== '/authproxy') {
          $rootScope.$broadcast('app:login_prompt_spawn');
        }

        return $q.reject(rejection);
      }
    }
  }]);

angular.module('checkmate.reAuth')
  .config(['$httpProvider', function($httpProvider) {
    'use strict';

    $httpProvider.interceptors.push('authHttpResponseInterceptor');
  }]);
