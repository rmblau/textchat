from uuid import uuid4

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import ForeignKey
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


class AppSetting(Base):
    """One global preference shared by every saved IRC profile."""

    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)


class Channels(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_name = Column(String, unique=True)
    display_name = Column(String, nullable=True)
    server_id = Column(Integer, ForeignKey("server.id"), nullable=True, index=True)

    def __init__(self, channel_name, server_id=None):
        self.channel_name = (
            f"{server_id}:{channel_name.casefold()}"
            if server_id is not None
            else channel_name
        )
        self.display_name = channel_name
        self.server_id = server_id


class ServerInfo(Base):
    __tablename__ = "server"
    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_name = Column(String, nullable=True)
    # Retained as a unique internal key for databases created by earlier
    # releases. Use ``connection_address`` for the actual IRC endpoint.
    server_address = Column(String, unique=True)
    connection_address = Column(String, nullable=True)
    port = Column(Integer, unique=False)
    nickname = Column(String, unique=False)
    password = Column(String, unique=False)
    sasl_login = Column(Boolean, unique=False)
    znc_username = Column(String, nullable=True)
    znc_network = Column(String, nullable=True)
    use_tls = Column(Boolean, default=False)
    is_active = Column(Boolean, default=False, nullable=False)

    def __init__(
        self,
        profile_name,
        server_address,
        port,
        nickname,
        password,
        sasl_login,
        znc_username=None,
        znc_network=None,
        use_tls=False,
        is_active=False,
    ):
        self.profile_name = profile_name
        self.server_address = f"profile-{uuid4().hex}"
        self.connection_address = server_address
        self.port = port
        self.nickname = nickname
        self.password = password
        self.sasl_login = sasl_login
        self.znc_username = znc_username
        self.znc_network = znc_network
        self.use_tls = use_tls
        self.is_active = is_active


async def create_table():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        result = await conn.exec_driver_sql("PRAGMA table_info(server)")
        existing_columns = {row[1] for row in result}

        migrations = {
            "znc_username": "TEXT",
            "znc_network": "TEXT",
            "use_tls": "BOOLEAN NOT NULL DEFAULT 0",
            "profile_name": "TEXT",
            "is_active": "BOOLEAN NOT NULL DEFAULT 0",
            "connection_address": "TEXT",
        }

        for column, sql_type in migrations.items():
            if column not in existing_columns:
                await conn.exec_driver_sql(
                    f"ALTER TABLE server ADD COLUMN {column} {sql_type}"
                )

        await conn.exec_driver_sql(
            "UPDATE server SET profile_name = server_address "
            "WHERE profile_name IS NULL OR profile_name = ''"
        )
        await conn.exec_driver_sql(
            "UPDATE server SET connection_address = server_address "
            "WHERE connection_address IS NULL OR connection_address = ''"
        )
        await conn.exec_driver_sql(
            """
            UPDATE server
            SET is_active = 1
            WHERE id = (SELECT MAX(id) FROM server)
              AND NOT EXISTS (SELECT 1 FROM server WHERE is_active = 1)
            """
        )

        channel_columns_result = await conn.exec_driver_sql(
            "PRAGMA table_info(channels)"
        )
        channel_columns = {row[1] for row in channel_columns_result}
        if "server_id" not in channel_columns:
            await conn.exec_driver_sql(
                "ALTER TABLE channels ADD COLUMN server_id INTEGER"
            )
            await conn.exec_driver_sql(
                """
                UPDATE channels
                SET server_id = (
                    SELECT id FROM server
                    WHERE is_active = 1
                    ORDER BY id DESC
                    LIMIT 1
                )
                """
            )

        channel_columns_result = await conn.exec_driver_sql(
            "PRAGMA table_info(channels)"
        )
        channel_columns = {row[1] for row in channel_columns_result}
        if "display_name" not in channel_columns:
            # Keep the existing unique column as an internal profile-scoped
            # key, while retaining the human-readable IRC channel separately.
            await conn.exec_driver_sql(
                "ALTER TABLE channels ADD COLUMN display_name TEXT"
            )
            await conn.exec_driver_sql(
                "UPDATE channels SET display_name = channel_name"
            )
            await conn.exec_driver_sql(
                """
                UPDATE channels
                SET channel_name =
                    CAST(COALESCE(server_id, 0) AS TEXT) || ':' ||
                    LOWER(channel_name)
                """
            )
