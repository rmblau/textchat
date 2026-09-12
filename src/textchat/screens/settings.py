from textchat.db.base import create_table
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button
from textual.widgets import Checkbox
from textual.widgets import Footer
from textual.widgets import Input
from textual.widgets import Label

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
            Label("Connect to IRC", classes="settings-title"),
            Label(
                "Enter your server and nickname. Channels are optional; "
                "ZNC restores its configured channels automatically.",
                classes="settings-help",
            ),
            Label("Server", classes="settings-label"),
            ServerAddress(placeholder="irc.example.net"),
            ServerPort(placeholder="Port (for example, 6697)", type="integer"),
            Label("Nickname", classes="settings-label"),
            Nickname(placeholder="Your nickname"),
            Label("ZNC (optional)", classes="settings-label"),
            Input(placeholder="ZNC username (optional)", id="znc_username"),
            Input(placeholder="ZNC network (optional)", id="znc_network"),
            Checkbox("Use TLS", False, id="use_tls"),
            Label("Channels (optional)", classes="settings-label"),
            Channels(placeholder="#channel, #another-channel"),
            Label("Password (optional)", classes="settings-label"),
            Password(placeholder="Server or ZNC password", password=True),
            Checkbox("SASL", False, id="sasl_login"),
            Button(label="Save and connect", id="save"),
            id="settings-form",
        )
        yield Footer()

    async def on_mount(self):
        await create_table()
        server = await ChannelOperations().get_server_info()
        if server is None:
            return

        self.query_one(ServerAddress).value = server.server_address
        self.query_one(ServerPort).value = str(server.port)
        self.query_one(Nickname).value = server.nickname
        self.query_one(Channels).value = ", ".join(await load_channels())
        self.query_one(Password).value = server.password or ""
        self.query_one("#znc_username", Input).value = server.znc_username or ""
        self.query_one("#znc_network", Input).value = server.znc_network or ""
        self.query_one("#use_tls", Checkbox).value = bool(server.use_tls)
        self.query_one("#sasl_login", Checkbox).value = bool(server.sasl_login)
        self.query_one("#save", Button).label = "Save settings"

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "save":
            server_address = self.query_one(ServerAddress).value.strip()
            server_port = self.query_one(ServerPort).value.strip()
            nickname = self.query_one(Nickname).value.strip()
            channels = self.query_one(Channels).value
            password = self.query_one(Password).value
            znc_username = self.query_one("#znc_username", Input).value or None
            znc_network = self.query_one("#znc_network", Input).value or None
            use_tls = self.query_one("#use_tls", Checkbox).value
            sasl_login = self.query_one("#sasl_login", Checkbox).value

            if not server_address or not server_port or not nickname:
                self.notify("Server, port, and nickname are required.")
                return

            try:
                port = int(server_port)
            except ValueError:
                self.notify("Port must be a number.")
                return

            if not 1 <= port <= 65535:
                self.notify("Port must be between 1 and 65535.")
                return

            await ChannelOperations().add_server_info(
                server_address,
                port,
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

            if not hasattr(self.app, "irc_client"):
                await self.app.action_return_home()
            else:
                self.notify("Settings saved. Restart to reconnect with them.")
                self.dismiss()
