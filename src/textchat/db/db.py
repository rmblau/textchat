from sqlalchemy import delete
from sqlalchemy import select

from .base import Channels
from .base import ServerInfo
from .base import Session


class ChannelOperations:
    async def get_channels(self):
        async with Session() as session:
            channels = await session.execute(select(Channels))
            await session.commit()
            channel_names = channels.scalars().all()
            return channel_names

    async def add_channel_to_list(self, channel):
        async with Session() as session:
            channel_name = Channels(channel_name=channel)
            session.add(channel_name)
            await session.commit()
        return channel_name

    async def get_server_info(self):
        async with Session() as session:
            result = await session.execute(
                select(ServerInfo).order_by(ServerInfo.id.desc())
            )
        return result.scalars().first()

    async def delete_channel(self, channel):
        async with Session() as session:
            stmt = await session.execute(
                delete(Channels).where(Channels.channel_name == channel)
            )
            await session.commit()
        return stmt

    async def add_server_info(
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
        async with Session() as session:
            result = await session.execute(
                select(ServerInfo).where(ServerInfo.server_address == server_address)
            )
        server_info = result.scalar_one_or_none()

        if server_info is None:
            server_info = ServerInfo(
                server_address,
                port,
                nickname,
                password,
                sasl_login,
                znc_username,
                znc_network,
                use_tls,
            )
            session.add(server_info)
        else:
            server_info.port = port
            server_info.nickname = nickname
            server_info.password = password
            server_info.sasl_login = sasl_login
            server_info.znc_username = znc_username
            server_info.znc_network = znc_network
            server_info.use_tls = use_tls

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
