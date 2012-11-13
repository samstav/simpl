from sqlalchemy import *
from migrate import *


meta = MetaData()

feedback = Table(
    'environments', meta,
    Column('dbid', Integer, primary_key=True, autoincrement=True),
    Column('id', String(32), index=True, unique=True),
    Column('body', Text)
)


def upgrade(migrate_engine):
    meta.bind = migrate_engine
    feedback.create()


def downgrade(migrate_engine):
    meta.bind = migrate_engine
    feedback.drop()

