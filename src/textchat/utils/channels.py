from ..db.db import get_channels
async def load_channels():
    channels = await get_channels()

    return [name.channel_name for name in channels]
