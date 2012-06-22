angular.module('checkmateServices', ['ngResource']).
  factory('Environment', function($resource){
    return $resource('/environments/:environmentId', {}, {
      query: {method:'GET', isArray:true}
    });
});