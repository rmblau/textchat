from ..db.db import ChannelOperations
async def load_channels():
    channels = await ChannelOperations().get_channels()

    return [name.channel_name for name in channels]
