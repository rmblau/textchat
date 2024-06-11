from sqlalchemy import select
from .base import Session, Channels, ServerInfo

async def get_channels():
    async with Session() as session:
        channels = await session.execute(select(Channels))
        await session.commit()
        channel_names = channels.scalars().all()
        return channel_names
    
async def add_channel_to_list(channel):
    async with Session() as session:
        channel_name = Channels(channel_name=channel)
        session.add(channel_name)
        await session.commit()
    return channel_name

async def add_server_info(server_address, port, nickname, password):
    async with Session() as session:
        server_info = ServerInfo(server_address, port, nickname, password)
        session.add(server_info)
        await session.commit()
    return server_info

async def get_username():
    async with Session() as session:
        username = await session.execute(select(ServerInfo.nickname))
        await session.commit()
        return username.scalars().first()
    
async def get_password():
    async with Session() as session:
        password = await session.execute(select(ServerInfo.password))
        await session.commit()
        return password.scalars().first()
    
async def get_port():
    async with Session() as session:
        port = await session.execute(select(ServerInfo.port))
        await session.commit()
        return port.scalars().first()

async def get_server_address():
    async with Session() as session:
        server_address = await session.execute(select(ServerInfo.server_address))
        await session.commit()
        return server_address.scalars().first()