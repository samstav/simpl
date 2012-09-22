checkmate = angular.module('checkmate', ['checkmateFilters', 'checkmateServices', 'ngSanitize', 'ui']);

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
  when('/', {
    templateUrl: 'partials/deployment-new.html',
    controller: DeploymentTryCtrl
  }).
  when('/deployments/:deploymentId', {
    templateUrl: 'partials/deployment-status.html',
    controller: DeploymentStatusCtrl
  }).
  when('/workflows/:workflowId/status', {
    templateUrl: 'partials/workflow-status.html',
    controller: WorkflowStatusCtrl
  }).
  when('/workflows/:workflowId/tasks/:taskId', {
    templateUrl: 'partials/workflow-task.html',
    controller: WorkflowTaskCtrl
  }).
  when('/providers', {
    templateUrl: 'partials/provider-list.html',
    controller: ProviderListCtrl
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
        x = $compile(value)(scope.$parent);
        debugger;
        element.html($compile(value)(scope.$parent));
      });
    }
  };
});


// TODO: Make this more permanent
var cm = cm ? cm : {};
cm.auth = (function() {
  var serviceCatalog = null;

  function setServiceCatalog(sc) {
    serviceCatalog = sc;
  }

  function getToken() {
    if (serviceCatalog === null) {
      return null;
    }

    return serviceCatalog.access.token.id;
  }

  function getTenant() {
    if (serviceCatalog === null) {
      return null;
    }

    return serviceCatalog.access.token.tenant.id;
  }

  function getUsername() {
    if (serviceCatalog === null) {
      return null;
    }

    return serviceCatalog.access.user.name;
  }

  function isAuthenticated() {
    if (serviceCatalog === null) {
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
    getUsername: getUsername,
    isAuthenticated: isAuthenticated
  };
}());

cm.Resource = (function() {

  function query($http, $scope, resource) {
    if (!$scope.signIn()) {
      throw "Not logged in";
    }
    return $http({
      method: 'GET',
      url: tenantUri() + resource,
      headers: getHeaders()
    });
  }

  function get($http, $scope, resource, id) {
    if (!$scope.signIn()) {
      throw "Not logged in";
    }
    return $http({
      method: 'GET',
      url: tenantUri() + resource + '/' + id,
      headers: getHeaders()
    });
  }

  function saveOrUpdate($http, $scope, resource, instance) {
    if (instance.id) {
      return $http({
        method: 'PUT',
        url: tenantUri() + resource + '/' + instance.id,
        headers: getHeaders(),
        data: JSON.stringify(instance)
      });
    } else {
      if (!$scope.signIn()) {
        throw "Not logged in";
      }

      return $http({
        method: 'POST',
        url: tenantUri() + resource,
        headers: getHeaders(),
        data: JSON.stringify(instance)
      });
    }
  }

  function del($http, $scope, resource, instance) {
    if (!$scope.signIn()) {
      throw "Not logged in";
    }
    return $http({
      method: 'DELETE',
      url: tenantId() + resource + '/' + instance.id,
      headers: getHeaders()
    });
  }

  // Privates

  function tenantUri() {
    tenant = cm.auth.getTenant();
    if (tenant !== null) {
      tenant = '/' + tenant + '/';
    } else {
      tenant = '/';
    }
    return tenant;
  }

  function getHeaders() {
    return {
      "X-Auth-Token": cm.auth.getToken()
    };
  }

  return {
    query: query,
    get: get,
    saveOrUpdate: saveOrUpdate,
    del: del
  };
}());

cm.Settings = (function() {

  function getSettingsFromBlueprint(bp) {
    var options = []; // The accumulating array

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
    var options = [];
    return options;
  }

  return {
    getSettingsFromBlueprint: getSettingsFromBlueprint,
    getSettingsFromEnvironment: getSettingsFromEnvironment
  };
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
    });
  }

  return {
    createGraph: createGraph
  };
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
};

//Initial Wordpress Template
WPBP = {
	"id": "d8fcfc17-b515-473a-9fe1-6d4e3356ef8d",
        "description": "uses MC config recipes which support blah...., multiple domains, ....",
        "services": {
            "lb": {
                "open-ports": [
                    "80/tcp"
                ],
                "component": {
                    "interface": "http",
                    "type": "load-balancer"
                },
                "relations": {
                    "web": "http",
                    "master": "http"
                },
                "exposed": true
            },
            "master": {
                "component": {
                    "type": "application",
                    "role": "master",
                    "name": "wordpress"
                },
                "relations": {
                    "backend": "mysql"
                },
                "constraints": [
                    {
                        "count": 1
                    }
                ]
            },
            "web": {
                "component": {
                    "type": "application",
                    "role": "web",
                    "name": "wordpress",
                    "options": [
                        {
                            "wordpress/version": "3.0.4"
                        }
                    ]
                },
                "relations": {
                    "master": "http",
                    "db": {
                        "interface": "mysql",
                        "service": "backend"
                    }
                }
            },
            "backend": {
                "component": {
                    "interface": "mysql",
                    "type": "database"
                }
            }
        },
        "options": {
            "ssl_certificate": {
                "sample": "-----BEGIN CERTIFICATE-----\nEncoded Certificate\n-----END CERTIFICATE-----\n",
                "constrains": [
                    {
                        "setting": "apache/ssl_certificate",
                        "service": "web",
                        "resource_type": "application"
                    }
                ],
                "type": "text",
                "description": "SSL certificate in PEM format. Make sure to include the BEGIN and END certificate lines.",
                "label": "SSL Certificate"
            },
            "domain": {
                "regex": "^(([a-zA-Z]|[a-zA-Z][a-zA-Z0-9\\-]*[a-zA-Z0-9])\\.)*([A-Za-z]|[A-Za-z][A-Za-z0-9\\-]*[A-Za-z0-9])$",
                "constrains": [
                    {
                        "setting": "apache/domain_name",
                        "service": "web",
                        "resource_type": "application"
                    }
                ],
                "description": "The domain you wish to host your blog on. (ex: example.com)",
                "label": "Domain",
                "sample": "example.com",
                "type": "string"
            },
            "database_memory": {
                "constrains": [
                    {
                        "setting": "memory",
                        "service": "backend",
                        "resource_type": "database"
                    }
                ],
                "description": "The size of the database instance in MB of RAM.",
                "default": 512,
                "label": "Database Size",
                "type": "select",
                "choice": [
                    {
                        "name": "512 Mb",
                        "value": 512
                    },
                    {
                        "name": "1024 Mb",
                        "value": 1024
                    },
                    {
                        "name": "2048 Mb",
                        "value": 2048
                    },
                    {
                        "name": "4096 Mb",
                        "value": 4096
                    }
                ]
            },
            "secure": {
                "type": "boolean",
                "description": "Make this a hardened deployment (you lose some flexibility)",
                "label": "secure"
            },
            "region": {
                "required": true,
                "type": "select",
                "label": "Region",
                "choice": [{
                    "name": "dallas", "value": "DFW"},
                    {"name": "chicago", "value": "ORD"}
                ]
            },
            "web_server_size": {
                "constrains": [
                    {
                        "setting": "size",
                        "service": "web",
                        "resource_type": "compute"
                    },
                    {
                        "setting": "size",
                        "service": "master",
                        "resource_type": "compute"
                    }
                ],
                "description": "The size of the instance in MB of RAM.",
                "default": 1024,
                "label": "Web Server Size",
                "type": "select",
                "choice": [
                    {
                        "name": "256 Mb",
                        "value": 256
                    },
                    {
                        "name": "512 Mb",
                        "value": 512
                    },
                    {
                        "name": "1 Gb",
                        "value": 1024
                    }
                ]
            },
            "web_server_count": {
                "constrains": [
                    {
                        "setting": "count",
                        "service": "web",
                        "resource_type": "compute"
                    }
                ],
                "description": "The number of WordPress servers (minimum two).",
                "default": 2,
                "label": "Number of Web Servers",
                "type": "int",
                "constraints": [
                    {
                        "greater-than": 1
                    }
                ]
            },
            "varnish": {
                "default": false,
                "constrains": [
                    {
                        "setting": "varnish/enabled",
                        "service": "web",
                        "resource_type": "application"
                    }
                ],
                "type": "boolean",
                "label": "Varnish Caching"
            },
            "database_volume_size": {
                "default": 1,
                "constrains": [
                    {
                        "setting": "disk",
                        "service": "backend",
                        "resource_type": "database"
                    }
                ],
                "type": "int",
                "description": "The hard drive space available for the database instance in GB.",
                "label": "Database Disk Size"
            },
            "ssl": {
                "default": false,
                "label": "SSL Enabled",
                "type": "boolean",
                "help": "If this option is selected, SSL keys need to be supplied as well. This option is\nalso currently mutually exclusive with the Varnish Caching option.\n",
                "description": "Use SSL to encrypt web traffic."
            },
            "prefix": {
                "constrains": [
                    {
                        "setting": "database/prefix",
                        "service": "web",
                        "resource_type": "application"
                    },
                    {
                        "setting": "user/name",
                        "service": "web",
                        "resource_type": "application"
                    },
                    {
                        "setting": "apache/user/name",
                        "service": "web",
                        "resource_type": "application"
                    },
                    {
                        "setting": "lsyncd/user/name",
                        "service": "web",
                        "resource_type": "application"
                    },
                    {
                        "setting": "database/name",
                        "service": "backend",
                        "resource_type": "database"
                    },
                    {
                        "setting": "database/username",
                        "service": "backend",
                        "resource_type": "database"
                    }
                ],
                "help": "Note that this also the user name, database name, and also identifies this\nwordpress install from other ones you might add later to the same deployment.\n",
                "default": "wp",
                "required": true,
                "label": "Prefix",
                "type": "string",
                "description": "The application ID (and wordpress table prefix)."
            },
            "ssl_private_key": {
                "sample": "-----BEGIN PRIVATE KEY-----\nEncoded key\n-----END PRIVATE KEY-----\n",
                "constrains": [
                    {
                        "setting": "apache/ssl_private_key",
                        "service": "web",
                        "resource_type": "application"
                    }
                ],
                "type": "string",
                "label": "SSL Certificate Private Key"
            },
            "path": {
                "constrains": [
                    {
                        "setting": "apache/path",
                        "service": "web",
                        "resource_type": "application"
                    },
                    {
                        "setting": "path",
                        "service": "web",
                        "resource_type": "application"
                    }
                ],
                "description": "The path you wish to host your blog on under your domain. (ex: /blog)",
                "default": "/",
                "label": "Path",
                "sample": "/blog",
                "type": "string"
            },
            "sample": {
                "constrains": [
                    {
                        "setting": "foo",
                        "service": "web",
                        "resource_type": "compute"
                    }
                ],
                "group": "advanced",
                "description": "The operating system of web servers.",
                "default": "Ubuntu 12.04",
                "uri": "/T1000/providers/...?type=type",
                "label": "Instance OS",
                "type": "uri"
            },
            "password": {
                "regex": "xxx",
                "type": "string",
                "description": "Password to use for service. Click the generate button to generate a random password.",
                "label": "Password"
            },
            "os": {
                "constrains": [
                    {
                        "setting": "os",
                        "service": "web",
                        "resource_type": "compute"
                    },
                    {
                        "setting": "os",
                        "service": "web",
                        "resource_type": "compute"
                    }
                ],
                "description": "The operating system for the web servers.",
                "default": "Ubuntu 11.10",
                "label": "Operating System",
                "type": "select",
                "choice": [
                    "Ubuntu 11.10",
                    "Ubuntu 12.04",
                    "CentOS",
                    "RHEL 6"
                ]
            },
            "register-dns": {
                "default": false,
                "type": "boolean",
                "label": "Register DNS Name"
            },
            "high_availability": {
                "type": "boolean",
                "description": "Insures your blog has higher uptimes by using redundant hardware (e.g. multuple servers)",
                "label": "High Availability"
            }
        },
        "name": "Scalable Wordpress (Managed Cloud Config)"
    };
//Default Environment
WPENV = {
        "description": "This environment tests legacy cloud servers. It is hard-targetted at chicago\nbecause the rackcloudtech legacy servers account is in chicago\n",
        "name": "Legacy Cloud Servers (ORD default)",
        "providers": {
            "legacy": {
                "catalog": {
                    "compute": {
                        "windows_instance": {
                            "is": "compute",
                            "id": "windows_instance",
                            "provides": [
                                {
                                    "compute": "windows"
                                }
                            ]
                        },
                        "linux_instance": {
                            "is": "compute",
                            "id": "linux_instance",
                            "provides": [
                                {
                                    "compute": "linux"
                                }
                            ]
                        }
                    },
                    "lists": {
                        "types": {
                            "24": {
                                "os": "Windows Server 2008 SP2 (64-bit)",
                                "name": "Windows Server 2008 SP2 (64-bit)"
                            },
                            "115": {
                                "os": "Ubuntu 11.04",
                                "name": "Ubuntu 11.04"
                            },
                            "31": {
                                "os": "Windows Server 2008 SP2 (32-bit)",
                                "name": "Windows Server 2008 SP2 (32-bit)"
                            },
                            "56": {
                                "os": "Windows Server 2008 SP2 (32-bit) + SQL Server 2008 R2 Standard",
                                "name": "Windows Server 2008 SP2 (32-bit) + SQL Server 2008 R2 Standard"
                            },
                            "120": {
                                "os": "Fedora 16",
                                "name": "Fedora 16"
                            },
                            "121": {
                                "os": "CentOS 5.8",
                                "name": "CentOS 5.8"
                            },
                            "122": {
                                "os": "CentOS 6.2",
                                "name": "CentOS 6.2"
                            },
                            "116": {
                                "os": "Fedora 15",
                                "name": "Fedora 15"
                            },
                            "125": {
                                "os": "Ubuntu 12.04 LTS",
                                "name": "Ubuntu 12.04 LTS"
                            },
                            "126": {
                                "os": "Fedora 17",
                                "name": "Fedora 17"
                            },
                            "119": {
                                "os": "Ubuntu 11.10",
                                "name": "Ubuntu 11.10"
                            },
                            "118": {
                                "os": "CentOS 6.0",
                                "name": "CentOS 6.0"
                            }
                        },
                        "sizes": {
                            "1": {
                                "disk": 10,
                                "name": "256 server",
                                "memory": 256
                            },
                            "3": {
                                "disk": 40,
                                "name": "1GB server",
                                "memory": 1024
                            },
                            "2": {
                                "disk": 20,
                                "name": "512 server",
                                "memory": 512
                            },
                            "5": {
                                "disk": 160,
                                "name": "4GB server",
                                "memory": 4096
                            },
                            "4": {
                                "disk": 80,
                                "name": "2GB server",
                                "memory": 2048
                            },
                            "7": {
                                "disk": 620,
                                "name": "15.5GB server",
                                "memory": 15872
                            },
                            "6": {
                                "disk": 320,
                                "name": "8GB server",
                                "memory": 8192
                            },
                            "8": {
                                "disk": 1200,
                                "name": "30GB server",
                                "memory": 30720
                            }
                        }
                    }
                },
                "vendor": "rackspace",
                "provides": [
                    {
                        "compute": "linux"
                    },
                    {
                        "compute": "windows"
                    }
                ]
            },
            "chef-local": {
                "vendor": "opscode",
                "provides": [
                    {
                        "application": "http"
                    },
                    {
                        "database": "mysql"
                    }
                ]
            },
            "common": {
                "vendor": "rackspace",
                "constraints": [
                    {
                        "region": "chicago"
                    }
                ]
            },
            "load-balancer": {
                "catalog": {
                    "lists": {
                        "regions": {
                            "DFW": "https://dfw.loadbalancers.api.rackspacecloud.com/v1.0/",
                            "ORD": "https://ord.loadbalancers.api.rackspacecloud.com/v1.0/"
                        }
                    },
                    "load-balancer": {
                        "http": {
                            "is": "load-balancer",
                            "id": "http",
                            "provides": [
                                {
                                    "load-balancer": "http"
                                }
                            ],
                            "options": "ref://id001"
                        },
                        "https": {
                            "is": "load-balancer",
                            "id": "https",
                            "provides": [
                                {
                                    "load-balancer": "https"
                                }
                            ],
                            "options": "ref://id001"
                        }
                    }
                },
                "endpoint": "https://lbaas.api.rackpsacecloud.com/loadbalancers/",
                "vendor": "rackspace",
                "provides": [
                    {
                        "load-balancer": "http"
                    }
                ]
            },
            "database": {
                "catalog": {
                    "compute": {
                        "mysql_instance": {
                            "is": "compute",
                            "id": "mysql_instance",
                            "provides": [
                                {
                                    "compute": "mysql"
                                }
                            ],
                            "options": {
                                "disk": {
                                    "type": "int",
                                    "unit": "Gb",
                                    "choice": [
                                        1,
                                        2,
                                        3,
                                        4,
                                        5,
                                        6,
                                        7,
                                        8,
                                        9,
                                        10
                                    ]
                                },
                                "memory": {
                                    "type": "int",
                                    "unit": "Mb",
                                    "choice": [
                                        512,
                                        1024,
                                        2048,
                                        4096
                                    ]
                                }
                            }
                        }
                    },
                    "lists": {
                        "regions": {
                            "DFW": "https://dfw.databases.api.rackspacecloud.com/v1.0/557366",
                            "ORD": "https://ord.databases.api.rackspacecloud.com/v1.0/557366"
                        },
                        "sizes": {
                            "1": {
                                "name": "m1.tiny",
                                "memory": 512
                            },
                            "3": {
                                "name": "m1.medium",
                                "memory": 2048
                            },
                            "2": {
                                "name": "m1.small",
                                "memory": 1024
                            },
                            "4": {
                                "name": "m1.large",
                                "memory": 4096
                            }
                        }
                    },
                    "database": {
                        "mysql_database": {
                            "is": "database",
                            "requires": [
                                {
                                    "compute": {
                                        "interface": "mysql",
                                        "relation": "host"
                                    }
                                }
                            ],
                            "id": "mysql_database",
                            "provides": [
                                {
                                    "database": "mysql"
                                }
                            ]
                        }
                    }
                },
                "vendor": "rackspace",
                "provides": [
                    {
                        "database": "mysql"
                    },
                    {
                        "compute": "mysql"
                    }
                ]
            }
        }
    };