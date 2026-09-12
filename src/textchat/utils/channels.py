from ..db.db import ChannelOperations


async def load_channels(server_id=None):
    channels = await ChannelOperations().get_channels(server_id)

    return [name.display_name or name.channel_name for name in channels]
