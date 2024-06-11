from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.sql.schema import MetaData
import asyncio
engine = create_async_engine(
    "sqlite+aiosqlite:///textchat.db", echo=False,)
Session = async_sessionmaker(
    bind=engine, expire_on_commit=False)
metadata = MetaData()
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass


class Channels(Base):
    __tablename__ = 'channels'

    id = Column(Integer, primary_key=True,
                autoincrement=True)
    channel_name = Column(String, unique=True)


    def __init__(self, channel_name):
        self.channel_name = channel_name

class ServerInfo(Base):
    __tablename__ = 'server'
    id = Column(Integer, primary_key=True, autoincrement=True)
    server_address = Column(String, unique=True)
    port = Column(Integer, unique=False)
    nickname = Column(String, unique=False)
    password = Column(String, unique=False)

    def __init__(self, server_address, port, nickname, password):
        self.server_address = server_address
        self.port = port
        self.nickname = nickname
        self.password = password


async def create_table():
    async with engine.begin() as conn:
       await conn.run_sync(Base.metadata.create_all)

