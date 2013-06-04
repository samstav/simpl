from sqlalchemy import *
from migrate import *


def upgrade(migrate_engine):
    meta = MetaData(bind=migrate_engine)

    deployments = Table('deployments', meta, autoload=True)
    created = Column('created', String(255), index=False)
    created.create(deployments)


def downgrade(migrate_engine):
    meta = MetaData(bind=migrate_engine)

    deployments = Table('deployments', meta, autoload=True)
    deployments.c.created.drop()
