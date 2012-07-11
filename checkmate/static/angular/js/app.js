checkmate = angular.module('checkmate', ['checkmateFilters', 'checkmateServices', 'ngSanitize'])

checkmate.config(['$routeProvider', function($routeProvider) {
  $routeProvider.
  when('/environments', {
    templateUrl: 'partials/environment-list.html',
    controller: EnvironmentListCtrl
  }).
  when('/environments/:environmentId', {
    templateUrl: 'partials/environment-detail.html',
    controller: EnvironmentDetailCtrl
  }).
  when('/profile', {
    templateUrl: 'partials/profile.html',
    controller: ProfileCtrl
  }).
  when('/blueprints', {
    templateUrl: 'partials/blueprint-list.html',
    controller: BlueprintListCtrl
  }).
  when('/blueprints/:blueprintId', {
    templateUrl: 'partials/blueprint-detail.html',
    controller: BlueprintDetailCtrl
  }).
  when('/deployments', {
    templateUrl: 'partials/deployment-list.html',
    controller: DeploymentListCtrl
  }).
  when('/deployments/new', {
    templateUrl: 'partials/deployment-new.html',
    controller: DeploymentNewCtrl
  }).
  when('/deployments/:deploymentId', {
    templateUrl: 'partials/deployment-status.html',
    controller: DeploymentStatusCtrl
  }).
  otherwise({
    redirectTo: '/'
  });
}]);

checkmate.directive('compileHtml', function($compile) {
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
  }
});


// TODO: Make this more permanent
var cm = cm ? cm : {};
cm.auth = (function() {
  var serviceCatalog = null;

  function setServiceCatalog(sc) {
    serviceCatalog = sc;
  }

  function getToken() {
    if (serviceCatalog == null) {
      return null;
    }

    return serviceCatalog.access.token.id;
  }

  function getTenant() {
    if (serviceCatalog == null) {
      return null;
    }

    return serviceCatalog.access.token.tenant.id;
  }

  function isAuthenticated() {
    if (serviceCatalog == null) {
      return false;
    }

    var expires = new Date(serviceCatalog.access.token.expires);
    var now = new Date();

    if (expires < now) {
      return false;
    }

    return true;
  }

  return {
    setServiceCatalog: setServiceCatalog,
    getToken: getToken,
    getTenant: getTenant,
    isAuthenticated: isAuthenticated
  }
}());

cm.Resource = (function() {

  function query($http, resource) {
    return $http({
      method: 'GET',
      url: tenantUri() + resource,
      headers: headers()
    });
  }

  function get($http, resource, id) {
    return $http({
      method: 'GET',
      url: tenantUri() + resource + '/' + id,
      headers: headers
    });
  }

  function saveOrUpdate($http, resource, instance) {
    if (instance.id == null) {
      return $http({
        method: 'POST',
        url: tenantUri() + resource,
        headers: headers,
        data: JSON.stringify(instance)
      });

    } else {
      return $http({
        method: 'PUT',
        url: tenantUri() + resource + '/' + instance.id,
        headers: headers,
        data: JSON.stringify(instance)
      });
    }
  }

  function del($http, resource, instance) {
    return $http({
      method: 'DELETE',
      url: tenantId() + resource + '/' + instance.id,
      headers: headers()
    });
  }

  // Privates

  function tenantUri() {
    return '/' + cm.auth.getTenant() + '/';
  }

  function headers() {
    return {
      "X-Auth-Token": cm.auth.getToken()
    };
  }

  return {
    query: query,
    get: get,
    saveOrUpdate: saveOrUpdate,
    del: del
  }
}());

cm.Settings = (function() {

  function getSettingsFromBlueprint(bp) {
    var options = new Array(); // The accumulating array

    var opts = bp.options;
    _.each(opts, function(option, key) {
      options.push($.extend({
        id: key
      }, option));
    });

    _.each(options, function(option) {
      if (option.regex) {
        if (!_.isRegExp(option.regex)) {
          console.log("Regex '" + option.regex + "' is invalid for setting " + option.id);
          delete option["regex"];
        }
      }
    });

    return options;
  }

  function getSettingsFromEnvironment(env) {
    var options = new Array();
    return options;
  }

  return {
    getSettingsFromBlueprint: getSettingsFromBlueprint,
    getSettingsFromEnvironment: getSettingsFromEnvironment
  }
}());

cm.graph = (function() {
  function createGraph(containerId, tasks) {
    var fd = new $jit.ForceDirected({  
      //id of the visualization container  
      injectInto: containerId,  
      //Enable zooming and panning  
      //with scrolling and DnD  
      Navigation: {  
        enable: true,  
        type: 'Native',  
        //Enable panning events only if we're dragging the empty  
        //canvas (and not a node).  
        panning: 'avoid nodes',  
        zooming: 10 //zoom speed. higher is more sensible  
      },  
      // Change node and edge styles such as  
      // color and width.  
      // These properties are also set per node  
      // with dollar prefixed data-properties in the  
      // JSON structure.  
      Node: {  
        overridable: true,  
        dim: 7  
      },  
      Edge: {  
        overridable: true,  
        color: '#23A4FF',  
        lineWidth: 0.4  
      },  
      // Add node events  
      Events: {  
        enable: true,  
        type: 'Native',  
        //Change cursor style when hovering a node  
        onMouseEnter: function() {  
          fd.canvas.getElement().style.cursor = 'move';  
        },  
        onMouseLeave: function() {  
          fd.canvas.getElement().style.cursor = '';  
        },  
        //Update node positions when dragged  
        onDragMove: function(node, eventInfo, e) {  
          var pos = eventInfo.getPos();  
          node.pos.setc(pos.x, pos.y);  
          fd.plot();  
        },  
        //Implement the same handler for touchscreens  
        onTouchMove: function(node, eventInfo, e) {  
          $jit.util.event.stop(e); //stop default touchmove event  
          this.onDragMove(node, eventInfo, e);  
        }  
      },  
      //Number of iterations for the FD algorithm  
      iterations: 200,  
      //Edge length  
      levelDistance: 130,  
      // This method is only triggered  
      // on label creation and only for DOM labels (not native canvas ones).  
      onCreateLabel: function(domElement, node){  
        // Create a 'name' and 'close' buttons and add them  
        // to the main node label  
        var nameContainer = document.createElement('span'),  
            closeButton = document.createElement('span'),  
            style = nameContainer.style;  
        nameContainer.className = 'name';  
        nameContainer.innerHTML = node.name;  
        domElement.appendChild(nameContainer);  
        style.fontSize = "0.9em";  
        style.color = "#ddd";  
        //Fade the node and its connections when  
        //clicking the close button  
        closeButton.onclick = function() {  
          node.setData('alpha', 0, 'end');  
          node.eachAdjacency(function(adj) {  
            adj.setData('alpha', 0, 'end');  
          });  
          fd.fx.animate({  
            modes: ['node-property:alpha',  
                    'edge-property:alpha'],  
            duration: 500  
          });  
        };  
        //Toggle a node selection when clicking  
        //its name. This is done by animating some  
        //node styles like its dimension and the color  
        //and lineWidth of its adjacencies.  
        nameContainer.onclick = function() {  
          //set final styles  
          fd.graph.eachNode(function(n) {  
            if(n.id != node.id) delete n.selected;  
            n.setData('dim', 7, 'end');  
            n.eachAdjacency(function(adj) {  
              adj.setDataset('end', {  
                lineWidth: 0.4,  
                color: '#23a4ff'  
              });  
            });  
          });  
          if(!node.selected) {  
            node.selected = true;  
            node.setData('dim', 17, 'end');  
            node.eachAdjacency(function(adj) {  
              adj.setDataset('end', {  
                lineWidth: 3,  
                color: '#36acfb'  
              });  
            });  
          } else {  
            delete node.selected;  
          }  
          //trigger animation to final styles  
          fd.fx.animate({  
            modes: ['node-property:dim',  
                    'edge-property:lineWidth:color'],  
            duration: 500  
          });  
          // Build the right column relations list.  
          // This is done by traversing the clicked node connections.  
          var list = [];  
          node.eachAdjacency(function(adj){  
            if(adj.getData('alpha')) list.push("<li class='temporary'>" + adj.nodeTo.name + "</li>");  
          });  
          //append connections information  
          $("#connections .temporary").remove();
          $("#connections").append(list.join(' '));
        };  
      },  
      // Change node styles when DOM labels are placed  
      // or moved.  
      onPlaceLabel: function(domElement, node){  
        var style = domElement.style;  
        var left = parseInt(style.left);  
        var top = parseInt(style.top);  
        var w = domElement.offsetWidth;  
        style.left = (left - w / 2) + 'px';  
        style.top = (top + 10) + 'px';  
        style.display = '';  
      }  
    });  
    // load JSON data.  
    fd.loadJSON(tasks);  
    // compute positions incrementally and animate.  
    fd.computeIncremental({  
      iter: 40,  
      property: 'end',  
      onStep: function(perc){  
        console.log(perc + '% loaded...');  
      },  
      onComplete: function(){  
        console.log('done');  
        fd.animate({  
          modes: ['linear'],  
          transition: $jit.Trans.Elastic.easeOut,  
          duration: 2500  
        });  
      }  
    })
  }
    
  return {
    createGraph: createGraph
  }
}());

PROVIDERS = {
  compute: {
    label: "Compute",
    options: [{
      id: "0505af50-a38d-012f-ead2-583062589e95",
      name: "Legacy Cloud Servers"
    }, {
      id: "19691970-a38d-012f-ead3-583062589e95",
      name: "Open Cloud Servers"
    }]
  },
  database: {
    label: "Database",
    options: [{
      id: "6701f550-a38d-012f-ead4-583062589e95",
      name: "Database as a Service"
    }, {
      id: "89632410-a38d-012f-ead5-583062589e95",
      name: "Open Cloud Servers"
    }]
  },
  lb: {
    label: "Load Balancing",
    options: [{
      id: "0000f550-a38d-012f-ead4-583062589e95",
      name: "Load Balancer as a Service"
    }, {
      id: "8643c410-a38d-012f-ead5-583062589e95",
      name: "Open Cloud Servers"
    }]
  }
}