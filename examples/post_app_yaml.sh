curl --data-binary @examples/app.yaml -H 'content-type: application/x-yaml'  http://localhost:8080/deployments -v

# Then get status: - you need the ID of the new deployment (or hard code it into app.yaml)
# curl -H 'Accept: application/x-yaml' http://localhost:8080/deployments/{id}/status -v

