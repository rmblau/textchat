from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy import update

from .base import AppSetting
from .base import Channels
from .base import ServerInfo
from .base import Session


class ChannelOperations:
    async def get_spellcheck_settings(self):
        defaults = {
            "enabled": True,
            "delay_ms": 500,
            "suggestion_limit": 3,
        }
        async with Session() as session:
            result = await session.execute(
                select(AppSetting).where(
                    AppSetting.key.in_(
                        [
                            "spellcheck_enabled",
                            "spellcheck_delay_ms",
                            "spellcheck_suggestion_limit",
                        ]
                    )
                )
            )
        values = {setting.key: setting.value for setting in result.scalars()}
        try:
            defaults["enabled"] = values.get("spellcheck_enabled", "true") == "true"
            defaults["delay_ms"] = int(values.get("spellcheck_delay_ms", 500))
            defaults["suggestion_limit"] = int(
                values.get("spellcheck_suggestion_limit", 3)
            )
        except ValueError:
            pass
        return defaults

    async def save_spellcheck_settings(self, enabled, delay_ms, suggestion_limit):
        values = {
            "spellcheck_enabled": str(bool(enabled)).lower(),
            "spellcheck_delay_ms": str(delay_ms),
            "spellcheck_suggestion_limit": str(suggestion_limit),
        }
        async with Session() as session:
            for key, value in values.items():
                setting = await session.get(AppSetting, key)
                if setting is None:
                    session.add(AppSetting(key=key, value=value))
                else:
                    setting.value = value
            await session.commit()
        return {
            "enabled": bool(enabled),
            "delay_ms": delay_ms,
            "suggestion_limit": suggestion_limit,
        }

    async def get_channels(self, server_id=None):
        async with Session() as session:
            statement = select(Channels).order_by(Channels.id)
            if server_id is not None:
                statement = statement.where(Channels.server_id == server_id)
            channels = await session.execute(statement)
            channel_names = channels.scalars().all()
            return channel_names

    async def add_channel_to_list(self, channel, server_id=None):
        async with Session() as session:
            channel_name = Channels(channel_name=channel, server_id=server_id)
            session.add(channel_name)
            await session.commit()
        return channel_name

    async def replace_channels(self, server_id, channels):
        """Replace the locally configured channel list for one server profile."""
        normalized = []
        seen = set()
        for channel in channels:
            channel = channel.strip()
            if channel and channel.casefold() not in seen:
                normalized.append(channel)
                seen.add(channel.casefold())

        async with Session() as session:
            await session.execute(
                delete(Channels).where(Channels.server_id == server_id)
            )
            session.add_all(
                Channels(channel_name=channel, server_id=server_id)
                for channel in normalized
            )
            await session.commit()

    async def get_server_info(self, server_id=None):
        async with Session() as session:
            statement = select(ServerInfo)
            if server_id is not None:
                statement = statement.where(ServerInfo.id == server_id)
            else:
                statement = statement.where(ServerInfo.is_active.is_(True)).order_by(
                    ServerInfo.id.desc()
                )
            result = await session.execute(statement)
        return result.scalars().first()

    async def get_servers(self):
        async with Session() as session:
            result = await session.execute(select(ServerInfo).order_by(ServerInfo.id))
        return result.scalars().all()

    async def set_active_server(self, server_id):
        async with Session() as session:
            await session.execute(update(ServerInfo).values(is_active=False))
            await session.execute(
                update(ServerInfo)
                .where(ServerInfo.id == server_id)
                .values(is_active=True)
            )
            await session.commit()

    async def delete_channel(self, channel, server_id=None):
        async with Session() as session:
            statement = delete(Channels).where(Channels.display_name == channel)
            if server_id is not None:
                statement = statement.where(Channels.server_id == server_id)
            stmt = await session.execute(statement)
            await session.commit()
        return stmt

    async def save_server(
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
        server_id=None,
    ):
        async with Session() as session:
            server_info = (
                await session.get(ServerInfo, server_id)
                if server_id is not None
                else None
            )
            if server_info is None:
                has_server = await session.scalar(select(ServerInfo.id).limit(1))
                server_info = ServerInfo(
                    profile_name,
                    server_address,
                    port,
                    nickname,
                    password,
                    sasl_login,
                    znc_username,
                    znc_network,
                    use_tls,
                    is_active=has_server is None,
                )
                session.add(server_info)
            else:
                server_info.profile_name = profile_name
                server_info.connection_address = server_address
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
