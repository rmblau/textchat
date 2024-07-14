from sqlalchemy import select, delete
from .base import Session, Channels, ServerInfo

class ChannelOperations:
    async def get_channels(self):
        async with Session() as session:
            channels = await session.execute(select(Channels))
            await session.commit()
            channel_names = channels.scalars().all()
            return channel_names
    
    async def add_channel_to_list(self,channel):
        async with Session() as session:
            channel_name = Channels(channel_name=channel)
            session.add(channel_name)
            await session.commit()
        return channel_name

    async def delete_channel(self,channel):
        async with Session() as session:
            stmt = await session.execute(delete(Channels).where(Channels.channel_name == channel))
            await session.commit()
        return stmt

    async def add_server_info(self,server_address, port, nickname, password, sasl_login):
        async with Session() as session:
            server_info = ServerInfo(server_address, port, nickname, password, sasl_login)
            session.add(server_info)
            await session.commit()
        return server_info

    async def get_username(self):
        async with Session() as session:
            username = await session.execute(select(ServerInfo.nickname))
            await session.commit()
        return username.scalars().first()
    
    async def get_password(self):
        async with Session() as session:
            password = await session.execute(select(ServerInfo.password))
            await session.commit()
        return password.scalars().first()
    
    async def get_port(self):
        async with Session() as session:
            port = await session.execute(select(ServerInfo.port))
            await session.commit()
        return port.scalars().first()

    async def get_server_address(self):
        async with Session() as session:
            server_address = await session.execute(select(ServerInfo.server_address))
            await session.commit()
            return server_address.scalars().first()
        
    async def get_sasl(self):
        async with Session() as session:
            sasl_login = await session.execute(select(ServerInfo.sasl_login))
            await session.commit()
        return sasl_login.scalars().first()
    