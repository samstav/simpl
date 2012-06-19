angular.module('checkmateServices', ['ngResource']).
    factory('Environment', function($resource){
  return $resource('/environments/:environmentId.json', {}, {
    query: {method:'GET', params:{environmentId:''}, isArray:true}
  });
});