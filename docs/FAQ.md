Q: What if I deploy a blueprint that uses CLoud Databases in a region that does not have Cloud Databases?

A: You'll get an error before the deployment runs.

If the blueprint has components that need a generic 'database' resource, you'll get a choice of DBaaS or compute instances with mysql on them (this is not coded yet). In the a region without DBaaS you'll just get the option to use compute instances. If the blueprint design is explicetly constrained to DBaaS (no compute instances with mysql allowed), then you'll get an error trying to deploy that blueprint in the DBaaS-less region. The error will happen in the planning phase, so no resources will be created.

This happens in a deployment, which combines an environment and a blueprint. The blueprint declares what it needs. The environment defines the account and what is available. When preparing a deployment, that's when the 'planning' happens and actual endpoints and resource availability are evaluated.

