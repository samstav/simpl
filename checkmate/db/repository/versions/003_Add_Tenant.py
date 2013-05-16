# Add the tenants and tags table
from sqlalchemy.schema import MetaData, Table, Column, ForeignKey,\
    UniqueConstraint
from sqlalchemy.types import String, Integer


def upgrade(migrate_engine):
    meta = MetaData(bind=migrate_engine)
    tenants = Table('tenants', meta,
                    Column('tenant_id', String(255), primary_key=True))
    tags = Table("tenant_tags", meta,
                 Column('id', Integer, primary_key=True, autoincrement=True),
                 Column('tenant_id', String(255),
                        ForeignKey('tenants.tenant_id',
                                   ondelete="CASCADE",
                                   onupdate="RESTRICT")),
                 Column('tag', String(255), index=True),
                 UniqueConstraint('tenant_id', 'tag'))
    tenants.create()
    tags.create()


def downgrade(migrate_engine):
    meta = MetaData(bind=migrate_engine)
    tenants = Table('tenants', meta, autoload=True)
    tags = Table("tenant_tags", meta, autoload=True)
    tags.drop()
    tenants.drop()
