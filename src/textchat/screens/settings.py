from sqlalchemy.exc import IntegrityError
from textchat.db.base import create_table
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button
from textual.widgets import Checkbox
from textual.widgets import Footer
from textual.widgets import Input
from textual.widgets import Label
from textual.widgets import Select

from ..db.db import ChannelOperations
from ..utils.channels import load_channels
from ..widgets.address import ServerAddress
from ..widgets.address import ServerPort
from ..widgets.channels import Channels
from ..widgets.nickname import Nickname
from ..widgets.password import Password


class SettingsScreen(Screen):
    """Create, select, and edit saved IRC server profiles."""

    def __init__(self):
        super().__init__()
        self.channel_ops = ChannelOperations()
        self.selected_server_id = None
        self._loading_profile = False

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-form"):
            yield Label("IRC server profiles", classes="settings-title")
            yield Label(
                "Choose a saved server to edit it, or create a new profile. "
                "Channels are optional; ZNC restores its configured channels.",
                classes="settings-help",
            )
            yield Label("Saved servers", classes="settings-label")
            yield Select(
                [],
                prompt="New server",
                allow_blank=True,
                id="server-selector",
            )
            with Horizontal(id="profile-actions"):
                yield Button("New server", id="new-server")
                yield Button("Save", id="save")
                yield Button("Save and reconnect", id="connect", variant="primary")
            yield Label("Profile name", classes="settings-label")
            yield Input(placeholder="e.g. Libera or Personal ZNC", id="profile_name")
            yield Label("Server", classes="settings-label")
            yield ServerAddress(placeholder="irc.example.net")
            yield ServerPort(placeholder="Port (for example, 6697)", type="integer")
            yield Label("Nickname", classes="settings-label")
            yield Nickname(placeholder="Your nickname")
            yield Label("ZNC (optional)", classes="settings-label")
            yield Input(placeholder="ZNC username (optional)", id="znc_username")
            yield Input(placeholder="ZNC network (optional)", id="znc_network")
            yield Checkbox("Use TLS", False, id="use_tls")
            yield Label("Channels (optional)", classes="settings-label")
            yield Channels(placeholder="#channel, #another-channel")
            yield Label("Password (optional)", classes="settings-label")
            yield Password(placeholder="Server or ZNC password", password=True)
            yield Checkbox("SASL", False, id="sasl_login")
        yield Footer()

    async def on_mount(self):
        await create_table()
        active_server = await self.channel_ops.get_server_info()
        await self._refresh_server_selector(
            active_server.id if active_server is not None else None
        )
        if active_server is not None:
            await self._load_server(active_server)
        else:
            self._clear_form()

    async def _refresh_server_selector(self, selected_server_id=None):
        servers = await self.channel_ops.get_servers()
        selector = self.query_one("#server-selector", Select)
        self._loading_profile = True
        selector.set_options(
            [
                (
                    f"{server.profile_name} — {server.connection_address}",
                    server.id,
                )
                for server in servers
            ]
        )
        if selected_server_id is not None:
            selector.value = selected_server_id
        self._loading_profile = False

    async def _load_server(self, server):
        self._loading_profile = True
        self.selected_server_id = server.id
        self.query_one("#profile_name", Input).value = server.profile_name or ""
        self.query_one(ServerAddress).value = server.connection_address
        self.query_one(ServerPort).value = str(server.port)
        self.query_one(Nickname).value = server.nickname
        self.query_one(Channels).value = ", ".join(await load_channels(server.id))
        self.query_one(Password).value = server.password or ""
        self.query_one("#znc_username", Input).value = server.znc_username or ""
        self.query_one("#znc_network", Input).value = server.znc_network or ""
        self.query_one("#use_tls", Checkbox).value = bool(server.use_tls)
        self.query_one("#sasl_login", Checkbox).value = bool(server.sasl_login)
        self._loading_profile = False

    def _clear_form(self):
        self._loading_profile = True
        self.selected_server_id = None
        self.query_one("#profile_name", Input).value = ""
        self.query_one(ServerAddress).value = ""
        self.query_one(ServerPort).value = "6697"
        self.query_one(Nickname).value = ""
        self.query_one(Channels).value = ""
        self.query_one(Password).value = ""
        self.query_one("#znc_username", Input).value = ""
        self.query_one("#znc_network", Input).value = ""
        self.query_one("#use_tls", Checkbox).value = False
        self.query_one("#sasl_login", Checkbox).value = False
        self._loading_profile = False

    @on(Select.Changed, "#server-selector")
    async def select_server(self, event: Select.Changed) -> None:
        if self._loading_profile or event.value == Select.NULL:
            return
        server = await self.channel_ops.get_server_info(event.value)
        if server is not None:
            await self._load_server(server)

    async def _save_server(self):
        profile_name = self.query_one("#profile_name", Input).value.strip()
        server_address = self.query_one(ServerAddress).value.strip()
        server_port = self.query_one(ServerPort).value.strip()
        nickname = self.query_one(Nickname).value.strip()
        channels = self.query_one(Channels).value.split(",")
        password = self.query_one(Password).value
        znc_username = self.query_one("#znc_username", Input).value or None
        znc_network = self.query_one("#znc_network", Input).value or None
        use_tls = self.query_one("#use_tls", Checkbox).value
        sasl_login = self.query_one("#sasl_login", Checkbox).value
        if not server_address or not server_port or not nickname:
            self.notify("Server, port, and nickname are required.")
            return None
        try:
            port = int(server_port)
        except ValueError:
            self.notify("Port must be a number.")
            return None
        if not 1 <= port <= 65535:
            self.notify("Port must be between 1 and 65535.")
            return None
        try:
            server = await self.channel_ops.save_server(
                profile_name or server_address,
                server_address,
                port,
                nickname,
                password,
                sasl_login,
                znc_username,
                znc_network,
                use_tls,
                self.selected_server_id,
            )
            await self.channel_ops.replace_channels(server.id, channels)
        except IntegrityError:
            self.notify("A saved server already uses that address. Edit it instead.")
            return None
        self.selected_server_id = server.id
        await self._refresh_server_selector(server.id)
        return server

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "new-server":
            self.query_one("#server-selector", Select).value = Select.NULL
            self._clear_form()
            return
        server = await self._save_server()
        if server is None:
            return
        if event.button.id == "save":
            self.notify(f"Saved {server.profile_name}.")
            return
        if self.app.current_mode != "settings":
            # Dismissal changes the screen stack immediately, but its visual
            # cleanup completes after this handler. Reconnect afterwards so
            # it always targets the visible IRC screen.
            self.dismiss()
            self.app.call_after_refresh(
                self.app.connect_saved_server,
                server.id,
            )
            return
        await self.app.connect_saved_server(server.id)
