angular.module('checkmate.redirectUri', []);

angular.module('checkmate.redirectUri')
  .factory('redirectUri', function($routeParams, $window) {
    'use strict';

    var allowedUris = ['waldo.rax.io'];
    var uri = $routeParams.redirect_uri;

    return redirect;

    /**
     * Searches for white-listed URIs and will consume redirect_uri.
     * @return {} A redirect or nothing.
     */
    function redirect() {
      if(uri) {
        _.each(allowedUris, function(allowedUri) {
          if(uri.indexOf(allowedUri) > -1) {
            return $window.location.href = uri;
          }
        }); 
      }

      return;
    }
  });