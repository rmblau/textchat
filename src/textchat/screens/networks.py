from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button
from textual.widgets import Label


class NetworkPickerScreen(ModalScreen[int | str]):
    """Let the user choose a saved IRC or ZNC network before connecting."""

    def __init__(self, servers) -> None:
        super().__init__()
        self.servers = servers

    def compose(self) -> ComposeResult:
        with Vertical(id="network-picker-dialog"):
            yield Label("Choose a network", id="network-picker-title")
            yield Label("Connect only when you select a saved profile.")

            for server in self.servers:
                endpoint = server.connection_address or server.server_address
                profile_name = server.profile_name or endpoint
                details = f"{endpoint}:{server.port}"
                if server.znc_network:
                    details += f" · ZNC network: {server.znc_network}"
                yield Button(
                    f"{profile_name} ({details})",
                    id=f"network-{server.id}",
                    classes="network-choice",
                )

            with Horizontal(id="network-picker-actions"):
                yield Button("Manage networks", id="settings")
                yield Button("Quit", id="quit", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("network-"):
            self.dismiss(int(button_id.removeprefix("network-")))
        elif button_id == "settings":
            self.dismiss("settings")
        else:
            self.app.exit()
