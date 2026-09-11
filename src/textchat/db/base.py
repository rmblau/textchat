from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql.schema import MetaData

engine = create_async_engine(
    "sqlite+aiosqlite:///textchat.db",
    echo=False,
)
Session = async_sessionmaker(bind=engine, expire_on_commit=False)
metadata = MetaData()


class Base(DeclarativeBase):
    pass


class Channels(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_name = Column(String, unique=True)

    def __init__(self, channel_name):
        self.channel_name = channel_name


class ServerInfo(Base):
    __tablename__ = "server"
    id = Column(Integer, primary_key=True, autoincrement=True)
    server_address = Column(String, unique=True)
    port = Column(Integer, unique=False)
    nickname = Column(String, unique=False)
    password = Column(String, unique=False)
    sasl_login = Column(Boolean, unique=False)
    znc_username = Column(String, nullable=True)
    znc_network = Column(String, nullable=True)
    use_tls = Column(Boolean, default=False)

    def __init__(
        self,
        server_address,
        port,
        nickname,
        password,
        sasl_login,
        znc_username=None,
        znc_network=None,
        use_tls=False,
    ):
        self.server_address = server_address
        self.port = port
        self.nickname = nickname
        self.password = password
        self.sasl_login = sasl_login
        self.znc_username = znc_username
        self.znc_network = znc_network
        self.use_tls = use_tls


async def create_table():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        result = await conn.exec_driver_sql("PRAGMA table_info(server)")
        existing_columns = {row[1] for row in result}

        migrations = {
            "znc_username": "TEXT",
            "znc_network": "TEXT",
            "use_tls": "BOOLEAN NOT NULL DEFAULT 0",
        }

        for column, sql_type in migrations.items():
            if column not in existing_columns:
                await conn.exec_driver_sql(
                    f"ALTER TABLE server ADD COLUMN {column} {sql_type}"
                )
