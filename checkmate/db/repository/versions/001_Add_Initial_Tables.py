from sqlalchemy import *
from migrate import *


meta = MetaData()

environments = Table(
    'environments', meta,
    Column('dbid', Integer, primary_key=True, autoincrement=True),
    Column('id', String(32), index=True, unique=True),
    Column('body', Text)
)

blueprints = Table(
    'blueprints', meta,
    Column('dbid', Integer, primary_key=True, autoincrement=True),
    Column('id', String(32), index=True, unique=True),
    Column('body', Text)
)

deployments = Table(
    'deployments', meta,
    Column('dbid', Integer, primary_key=True, autoincrement=True),
    Column('id', String(32), index=True, unique=True),
    Column('body', Text)
)

components = Table(
    'components', meta,
    Column('dbid', Integer, primary_key=True, autoincrement=True),
    Column('id', String(32), index=True, unique=True),
    Column('body', Text)
)

workflows = Table(
    'workflows', meta,
    Column('dbid', Integer, primary_key=True, autoincrement=True),
    Column('id', String(32), index=True, unique=True),
    Column('body', Text)
)


def upgrade(migrate_engine):
    meta.bind = migrate_engine
    environments.create()
    blueprints.create()
    deployments.create()
    components.create()
    workflows.create()


def downgrade(migrate_engine):
    meta.bind = migrate_engine
    workflows.drop()
    components.drop()
    deployments.drop()
    blueprints.drop()
    environments.drop()
