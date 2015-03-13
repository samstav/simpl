angular.module('checkmate.redirectUri', []);

angular.module('checkmate.redirectUri')
  .factory('redirectUri', function($routeParams, $window) {
    'use strict';

    return redirect;

    /**
     * Uses redirect_uri param for redirecting.
     * @return {} A redirect or nothing.
     */
    function redirect() {
      var uri = $routeParams.redirect_uri;

      if(uri) {
        return $window.location.href = uri;
      }

      return;
    }
  });