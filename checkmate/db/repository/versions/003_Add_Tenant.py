# Add the tenants and tags table
from sqlalchemy.schema import MetaData, Table, Column
from sqlalchemy.types import String, Text, Integer


def upgrade(migrate_engine):
    meta = MetaData(bind=migrate_engine)
    tenants = Table('tenants', meta,
                    Column('id', Integer, primary_key=True,
                           autoincrement=True),
                    Column('tenant_id', String(255), index=True, unique=True),
                    Column('tags', Text))
    tenants.create()


def downgrade(migrate_engine):
    meta = MetaData(bind=migrate_engine)
    tenants = Table('tenants', meta, autoload=True)
    tenants.drop()
