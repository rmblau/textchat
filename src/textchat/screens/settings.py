from textchat.db.base import create_table
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button
from textual.widgets import Checkbox
from textual.widgets import Footer
from textual.widgets import Input

from ..db.db import ChannelOperations
from ..utils.channels import load_channels
from ..widgets.address import ServerAddress
from ..widgets.address import ServerPort
from ..widgets.channels import Channels
from ..widgets.nickname import Nickname
from ..widgets.password import Password


class SettingsScreen(Screen):

    def compose(self) -> ComposeResult:
        yield Vertical(
            ServerAddress(placeholder="Server address"),
            ServerPort(placeholder="port", type="integer"),
            Nickname(placeholder="nickname"),
            Input(placeholder="ZNC username (optional)", id="znc_username"),
            Input(placeholder="ZNC network (optional)", id="znc_network"),
            Checkbox("Use TLS", False, id="use_tls"),
            Channels(placeholder="channels to join (seperate by comma)"),
            Password(placeholder="password", password=True),
            Checkbox("SASL", False, id="sasl_login"),
            Button(label="Save", id="save"),
            classes="column",
        )
        yield Footer()

    async def on_mount(self):
        await create_table()

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "save":
            server_address = self.query_one(ServerAddress).value
            server_port = self.query_one(ServerPort).value
            nickname = self.query_one(Nickname).value
            channels = self.query_one(Channels).value
            password = self.query_one(Password).value
            znc_username = self.query_one("#znc_username", Input).value or None
            znc_network = self.query_one("#znc_network", Input).value or None
            use_tls = self.query_one("#use_tls", Checkbox).value
            sasl_login = self.query_one("#sasl_login", Checkbox).value
            await ChannelOperations().add_server_info(
                server_address,
                server_port,
                nickname,
                password,
                sasl_login,
                znc_username,
                znc_network,
                use_tls,
            )
            existing_channnels = await load_channels()

            for channel in (item.strip() for item in channels.split(",")):
                if not channel:
                    continue

                if channel not in existing_channnels:
                    await ChannelOperations().add_channel_to_list(channel)
