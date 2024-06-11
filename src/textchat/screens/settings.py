from textchat.client import IRCApp
from textchat.db.base import create_table
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Input, Footer, Button
from textual.containers import Vertical
from ..widgets.address import ServerAddress, ServerPort
from ..widgets.nickname import Nickname
from ..widgets.channels import Channels
from ..widgets.password import Password
from ..db.db import add_channel_to_list, add_server_info
from ..utils.channels import load_channels

class SettingsScreen(Screen):
 
    def compose(self) -> ComposeResult:
        yield Vertical(
            ServerAddress(placeholder="Server address"),
            ServerPort(placeholder="port", type="integer"),
            Nickname(placeholder="nickname"),
            Channels(placeholder="channels to join (seperate by comma)"),
            Password(placeholder="password", password=True),
            Button(label="Save", id="save"),
            classes="column"
        )
        yield Footer()
    async def on_mount(self):
        await create_table()

    
    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id =="save":
            server_address = self.query_one(ServerAddress).value
            server_port = self.query_one(ServerPort).value
            nickname = self.query_one(Nickname).value
            channels = self.query_one(Channels).value
            password = self.query_one(Password).value
            await add_server_info(server_address, server_port, nickname, password)
            existing_channnels = await load_channels()
            for channel in channels.split(","):
             if channel not in existing_channnels:
                await add_channel_to_list(channel)
             else:
                pass
            self.irc_client = IRCApp(self,
                                 server_list=[(server_address, server_port)],
                                 nickname=nickname,
                                 realname=nickname,
                                 ident_password=password,
                                 channels=channels,
                                 )
            self.irc_client.start_event_loop()
