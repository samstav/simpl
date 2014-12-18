var catalogData = {
    "web": {
        "apache": {
            "requires": [
                {
                    "host": "linux"
                }
            ],
            "is": "web",
            "id": "apache",
            "provides": [
                {
                    "web": "apache"
                }
            ],
            "options": {
                "server_alias": {
                    "type": "array",
                    "example": [
                        "www.example.com",
                        "blog.example.com"
                    ],
                    "label": "Additional domain names to respond on"
                },
                "port": {
                    "default": 80,
                    "type": "integer",
                    "label": "Listening port"
                },
                "server_name": {
                    "type": "string",
                    "example": "example.com",
                    "label": "Site's domain name"
                }
            },
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/apache-small.png",
                    "tattoo": "/images/apache.png"
                }
            }
        },
        "nginx": {
            "is": "web",
            "requires": [
                {
                    "host": "linux"
                }
            ],
            "id": "nginx",
            "provides": [
                {
                    "web": "nginx"
                }
            ],
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/nginx.png",
                    "tattoo": "/images/nginx.png"
                }
            }
        }
    },
    "monitoring": {
        "new-relic": {
            "provides": [
                {
                    "monitoring": "new-relic"
                }
            ],
            "is": "monitoring",
            "requires": [
                {
                    "host": "linux"
                }
            ],
            "options": {
                "license": {
                    "type": "string",
                    "label": "New Relic license key"
                }
            },
            "id": "new-relic",
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/newrelic.png",
                    "tattoo": "/images/newrelic.png"
                }
            }
        },
        "rax-cloud-monitoring": {
            "provides": [
                {
                    "monitoring": "rackspace"
                }
            ],
            "is": "monitoring",
            "requires": [],
            "options": {
            },
            "id": "rax-cloud-monitoring",
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/icon-monitoring.svg",
                    "tattoo": "/images/icon-monitoring.svg"
                }
            }
        }
    },
    "database": {
        "mongodb": {
            "provides": [
                {
                    "database": "mongodb"
                }
            ],
            "is": "database",
            "requires": [
                {
                    "host": "linux"
                }
            ],
            "options": {
                "port": {
                    "type": "integer",
                    "label": "Listening port"
                }
            },
            "id": "mongodb",
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/mongodb-icon-20x20.png",
                    "tattoo": "/images/mongodb-tattoo.png"
                }
            }
        },
        "postgres": {
            "is": "database",
            "requires": [
                {
                    "host": "linux"
                }
            ],
            "id": "postgres",
            "provides": [
                {
                    "database": "postgres"
                }
            ],
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/postgres-icon.png",
                    "tattoo": "/images/postgre_sql_256.png"
                }
            }
        },
        "mysql": {
            "is": "database",
            "id": "mysql",
            "provides": [
                {
                    "database": "mysql"
                }
            ],
            "requires": [
                {
                    "host": "linux"
                }
            ],
            "options": {
                "server_root_password": {
                    "default": "=generate_password(min_length=12, required_chars=[\"0123456789\", \"abcdefghijklmnopqrstuvwxyz\", \"ABCDEFGHIJKLMNOPQRSTUVWXYZ\"])",
                    "required": true,
                    "type": "password",
                    "display-hints": {
                      "group": "application",
                      "order": 1
                    },
                    "constraints": [
                      {
                        "regex": "^((.){8,255})?$",
                        "message": "must be between 8 and 255 characters long if provided"
                      }
                    ]
                },
                "username": {
                    "default": "root",
                    "required": true,
                    "type": "string",
                    "display-hints": {
                      "group": "application",
                      "order": 2
                    }
                },
                "password": {
                    "default": "=generate_password(min_length=12, required_chars=[\"0123456789\", \"abcdefghijklmnopqrstuvwxyz\", \"ABCDEFGHIJKLMNOPQRSTUVWXYZ\"])",
                    "required": true,
                    "type": "password",
                    "display-hints": {
                      "group": "application",
                      "order": 3
                    },
                    "constraints": [
                      {
                        "regex": "^((.){8,255})?$",
                        "message": "must be between 8 and 255 characters long if provided"
                      }
                    ]
                }
            },
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/mysql-small.png",
                    "tattoo": "/images/mysql-tattoo.png"
                }
            }
        },
        "mysql#slave": {
            "is": "database",
            "id": "mysql-slave",
            "provides": [
                {
                    "database": "mysql#slave"
                }
            ],
            "requires": [
                {
                    "host": "linux"
                }, {
                    "database": "mysql#master"
                }
            ],
            "options": {
                "server_root_password": {
                    "default": "=generate_password(min_length=12, required_chars=[\"0123456789\", \"abcdefghijklmnopqrstuvwxyz\", \"ABCDEFGHIJKLMNOPQRSTUVWXYZ\"])",
                    "required": true,
                    "type": "password",
                    "display-hints": {
                      "group": "application",
                      "order": 1
                    },
                    "constraints": [
                      {
                        "regex": "^((.){8,255})?$",
                        "message": "must be between 8 and 255 characters long if provided"
                      }
                    ]
                },
                "username": {
                    "default": "root",
                    "required": true,
                    "type": "string",
                    "display-hints": {
                      "group": "application",
                      "order": 2
                    }
                },
                "password": {
                    "default": "=generate_password(min_length=12, required_chars=[\"0123456789\", \"abcdefghijklmnopqrstuvwxyz\", \"ABCDEFGHIJKLMNOPQRSTUVWXYZ\"])",
                    "required": true,
                    "type": "password",
                    "display-hints": {
                      "group": "application",
                      "order": 3
                    },
                    "constraints": [
                      {
                        "regex": "^((.){8,255})?$",
                        "message": "must be between 8 and 255 characters long if provided"
                      }
                    ]
                }
            },
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/mysql-small.png",
                    "tattoo": "/images/mysql-tattoo.png"
                }
            }
        },
        "mysql#master": {
            "is": "database",
            "id": "mysql-master",
            "provides": [
                {
                    "database": "mysql#master"
                }
            ],
            "requires": [
                {
                    "host": "linux"
                }
            ],
            "options": {
                "server_root_password": {
                    "default": "=generate_password(min_length=12, required_chars=[\"0123456789\", \"abcdefghijklmnopqrstuvwxyz\", \"ABCDEFGHIJKLMNOPQRSTUVWXYZ\"])",
                    "required": true,
                    "type": "password",
                    "display-hints": {
                      "group": "application",
                      "order": 1
                    },
                    "constraints": [
                      {
                        "regex": "^((.){8,255})?$",
                        "message": "must be between 8 and 255 characters long if provided"
                      }
                    ]
                },
                "username": {
                    "default": "root",
                    "required": true,
                    "type": "string",
                    "display-hints": {
                      "group": "application",
                      "order": 2
                    }
                },
                "password": {
                    "default": "=generate_password(min_length=12, required_chars=[\"0123456789\", \"abcdefghijklmnopqrstuvwxyz\", \"ABCDEFGHIJKLMNOPQRSTUVWXYZ\"])",
                    "required": true,
                    "type": "password",
                    "display-hints": {
                      "group": "application",
                      "order": 3
                    },
                    "constraints": [
                      {
                        "regex": "^((.){8,255})?$",
                        "message": "must be between 8 and 255 characters long if provided"
                      }
                    ]
                }
            },
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/mysql-small.png",
                    "tattoo": "/images/mysql-tattoo.png"
                }
            }
        },
        "rsCloudDb": {
            "is": "database",
            "id": "rsCloudDb",
            "provides": [
                {
                    "database": "mysql"
                }
            ],
            "requires": [
                {
                    "compute": "mysql"
                }
            ],
            "options": {
                "server_root_password": {
                    "default": "=generate_password(min_length=12, required_chars=[\"0123456789\", \"abcdefghijklmnopqrstuvwxyz\", \"ABCDEFGHIJKLMNOPQRSTUVWXYZ\"])",
                    "required": true,
                    "type": "password",
                    "display-hints": {
                      "group": "application",
                      "order": 1
                    },
                    "constraints": [
                      {
                        "regex": "^((.){8,255})?$",
                        "message": "must be between 8 and 255 characters long if provided"
                      }
                    ]
                },
                "username": {
                    "default": "root",
                    "required": true,
                    "type": "string",
                    "display-hints": {
                      "group": "application",
                      "order": 2
                    }
                },
                "password": {
                    "default": "=generate_password(min_length=12, required_chars=[\"0123456789\", \"abcdefghijklmnopqrstuvwxyz\", \"ABCDEFGHIJKLMNOPQRSTUVWXYZ\"])",
                    "required": true,
                    "type": "password",
                    "display-hints": {
                      "group": "application",
                      "order": 3
                    },
                    "constraints": [
                      {
                        "regex": "^((.){8,255})?$",
                        "message": "must be between 8 and 255 characters long if provided"
                      }
                    ]
                }
            },
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/icon-databases.svg",
                    "tattoo": "/images/icon-databases.svg"
                }
            }
        }
    },
    "cache": {
        "varnish": {
            "is": "cache",
            "requires": [
                {
                    "host": "linux"
                }
            ],
            "id": "varnish",
            "provides": [
                {
                    "cache": "varnish"
                }
            ],
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/varnish.jpg",
                    "tattoo": "/images/varnish.jpg"
                }
            }
        },
        "memcached": {
            "provides": [
                {
                    "cache": "memcache"
                }
            ],
            "is": "cache",
            "requires": [
                {
                    "host": "linux"
                }
            ],
            "options": {
                "monitoring": {
                    "default": false,
                    "type": "boolean",
                    "label": "Enable monitoring"
                },
                "port": {
                    "type": "integer",
                    "label": "Listening port"
                }
            },
            "id": "memcached",
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/memcached-icon-20x20.png",
                    "tattoo": "/images/memcached-tattoo.png"
                }
            }
        },
        "redis": {
            "provides": [
                {
                    "cache": "redis"
                }
            ],
            "is": "cache",
            "requires": [
                {
                    "host": "linux"
                }
            ],
            "options": {
                "port": {
                    "type": "integer",
                    "label": "Listening port"
                }
            },
            "id": "redis",
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/redis-icon-20x20.png",
                    "tattoo": "/images/redis-tattoo.png"
                }
            }
        }
    },
    "storage": {
        "gluster": {
            "is": "storage",
            "requires": [
                {
                    "host": "linux"
                }
            ],
            "id": "gluster",
            "provides": [
                {
                    "storage": "gluster"
                }
            ],
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/glusterfs-icon-20x20.png",
                    "tattoo": "/images/glusterfs-tattoo.png"
                }
            }
        },
        "rax-cloud-files": {
            "is": "storage",
            "id": "rax-cloud-files",
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/icon-files.svg",
                    "tattoo": "/images/icon-files.svg"
                }
            }
        }
    },
    "application": {
        "app": {
            "is": "application",
            "id": "app",
            "provides": [
                {
                    "application": "http"
                }
            ],
            "requires": [
                {
                    "host": "linux"
                }
            ],
            "options": {
                "demo": {
                    "type": "boolean",
                    "label": "Enable Demo"
                },
                "packages": {
                    "type": "string",
                    "label": "PHP Packages"
                }
            },
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/github.ico",
                    "tattoo": "/images/github-tattoo.png"
                }
            }
        },
        "asp.net": {
            "is": "application",
            "id": "asp.net",
            "provides": [
                {
                    "application": "http"
                }
            ],
            "requires": [
                {
                    "host": "windows"
                }
            ],
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/asp-net-icon-20x20.png",
                    "tattoo": "/images/asp-net-tattoo.png"
                }
            }
        },
        "wordpress": {
            "is": "application",
            "id": "wordpress",
            "provides": [
                {
                    "application": "http"
                }
            ],
            "requires": [
                {
                    "host": "linux"
                }, {
                    "database": "mysql"
                }
            ],
            "options": {
                "prefix": {
                    "type": "string",
                    "label": "Prefix"
                },
                "url": {
                  "label": "Site Address",
                  "description": "The address you wish to host your blog on.",
                  "type": "url",
                  "required": true,
                  "default": "http://example.com/",
                  "display-hints": {
                    "group": "application",
                    "order": 1,
                    "default-protocol": "http",
                    "encrypted-protocols": [
                      "https"
                    ],
                    "sample": "http://example.com/"
                  },
                  "constraints": [
                    {
                      "protocols": [
                        "http",
                        "https"
                      ],
                      "message": "must be a supported protocol"
                    },
                    {
                      "regex": "^([a-zA-Z]{2,}?\\:\\/\\/[a-zA-Z0-9\\-]+(?:\\.[a-zA-Z0-9\\-]+)*\\.[a-zA-Z]{2,16}(?:\\/?|(?:\\/[\\w\\-]+)*)(?:\\/?|\\/\\w+\\.[a-zA-Z]{2,4}(?:\\?[\\w]+\\=[\\w\\-]+)?)?(?:\\&[\\w]+\\=[\\w\\-]+)*)$",
                      "message": "must be a valid web address"
                    }
                  ]
                }
            },
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/wordpress-icon-20x20.png",
                    "tattoo": "/images/wordpress-tattoo.png"
                }
            }
        }
    },
    "load-balancer": {
        "rsCloudLB": {
            "is": "load-balancer",
            "id": "rsCloudLB",
            "provides": [
                {"load-balancer": "vip"},
                {"load-balancer": "http"},
                {"load-balancer": "https"}
            ],
            "requires": [
                {"application": "http"}
            ],
            "options": {
                "algorithm": {
                    "type": "list",
                    "choice": ["http", "https"]
                },
                "create_dns": {
                    "type": "boolean",
                    "default": false
                },
                "allow_insecure": {
                    "type": "boolean",
                    "default": false
                }
            },
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/icon-load-balancers.svg",
                    "tattoo": "/images/icon-load-balancers.svg"
                }
            }
        }
    },
    "dns": {
        "rax:dns": {
            "is": "dns",
            "id": "rax:dns",
            "meta-data": {
                "display-hints": {
                    "icon-20x20": "/images/icon-dns.svg",
                    "tattoo": "/images/icon-dns.svg"
                }
            }
        }
    }
};

angular.module('checkmate.Catalog', []);
angular.module('checkmate.Catalog')
  .factory('Catalog', function() {
    var Catalog = {
      'data': {},
      'components': {}
    };

    Catalog.get = function() {
      return this.data;
    };

    Catalog.set = function(data) {
      var components = {};

      // This sets the component map.
      angular.forEach(data, function(_components, _service) {
        angular.forEach(_components, function(_component) {
          components[_component.id] = _component;
        });
      });

      this.components = angular.extend(this.components, components);
      this.data = data;
    };

    Catalog.getComponents = function() {
      return this.components;
    };

    Catalog.getComponent = function(name) {
      return this.components[name];
    };

    Catalog.set(window.catalogData);

    return Catalog;

  });
