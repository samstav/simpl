# Save an environment
curl -d "environment:
  name: Production
  providers:
  - compute: &rax-cloud-servers
    endpoint: https://servers.api.rakcpsacecloud.com/servers/{tenantId}
  - loadbalancer: &rax-lbaas
    endpoint: https://lbaas.api.rakcpsacecloud.com/servers/{tenantId}
  - database: &rax-dbaas
    endpoint: https://database.api.rakcpsacecloud.com/servers/{tenantId}
  - common:
    vendor: rackspace
    credentials:
    - token: {token}" -H 'content-type: application/x-yaml' http://localhost:8080/environments

# With ID
curl -d "environment:
  id: 1
  name: Production
  providers:
  - compute: &rax-cloud-servers
    endpoint: https://servers.api.rakcpsacecloud.com/servers/{tenantId}
  - loadbalancer: &rax-lbaas
    endpoint: https://lbaas.api.rakcpsacecloud.com/servers/{tenantId}
  - database: &rax-dbaas
    endpoint: https://database.api.rakcpsacecloud.com/servers/{tenantId}
  - common:
    vendor: rackspace
    credentials:
    - token: {token}" -H 'content-type: application/x-yaml' http://localhost:8080/environments

# Get the first seed environment (in json, default)
curl http://localhost:8080/environments/1

# Get that environment in yaml
curl -H 'Accept: application/x-yaml' http://localhost:8080/environments/1

# Save a new deployment
curl -d "deployment:
  id: 1001
  blueprint: http://127.0.0.1:8080/components/wordpress
  environment: #*env1
  inputs:
    domain: rackcloudtech.com
    ssl: false" -H 'content-type: application/x-yaml' http://localhost:8080/deployments

# Execute deployment
# curl -X POST http://localhost:8080/deployments/1001/build

# Get status
curl http://localhost:8080/deployments/1001/status

