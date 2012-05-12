from sqlalchemy import *
from migrate import *


def upgrade(migrate_engine):
    meta = MetaData(bind=migrate_engine)
    environments = Table('environments', meta, autoload=True)
    secrets = Column('secrets', Text)
    secrets.create(environments)
    tenant_id = Column('tenant_id', String(255))
    tenant_id.create(environments)

    blueprints = Table('blueprints', meta, autoload=True)
    secrets = Column('secrets', Text)
    secrets.create(blueprints)
    tenant_id = Column('tenant_id', String(255))
    tenant_id.create(blueprints)

    components = Table('components', meta, autoload=True)
    secrets = Column('secrets', Text)
    secrets.create(components)
    tenant_id = Column('tenant_id', String(255))
    tenant_id.create(components)

    deployments = Table('deployments', meta, autoload=True)
    secrets = Column('secrets', Text)
    secrets.create(deployments)
    tenant_id = Column('tenant_id', String(255))
    tenant_id.create(deployments)

    workflows = Table('workflows', meta, autoload=True)
    secrets = Column('secrets', Text)
    secrets.create(workflows)
    tenant_id = Column('tenant_id', String(255))
    tenant_id.create(workflows)


def downgrade(migrate_engine):
    meta = MetaData(bind=migrate_engine)
    environments = Table('environments', meta, autoload=True)
    environments.c.secrets.drop()
    environments.c.tenant_id.drop()

    blueprints = Table('blueprints', meta, autoload=True)
    blueprints.c.secrets.drop()
    blueprints.c.tenant_id.drop()

    components = Table('components', meta, autoload=True)
    components.c.secrets.drop()
    components.c.tenant_id.drop()

    deployments = Table('deployments', meta, autoload=True)
    deployments.c.secrets.drop()
    deployments.c.tenant_id.drop()

    workflows = Table('workflows', meta, autoload=True)
    workflows.c.secrets.drop()
    workflows.c.tenant_id.drop()
