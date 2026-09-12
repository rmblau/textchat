from textchat.client import WhoisInfo
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button
from textual.widgets import Label


class WhoisScreen(ModalScreen[None]):
    """Display the completed server response for a WHOIS request."""

    def __init__(self, info: WhoisInfo) -> None:
        super().__init__()
        self.info = info

    @staticmethod
    def _format_idle(seconds: int) -> str:
        minutes, _ = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        if days:
            return f"{days}d {hours}h {minutes}m"
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    def compose(self) -> ComposeResult:
        with Vertical(id="whois-dialog"):
            yield Label(self.info.nickname, id="whois-title", markup=False)

            if self.info.error:
                yield Label(self.info.error, classes="whois-error", markup=False)
            else:
                if self.info.username and self.info.hostname:
                    yield Label(
                        f"User: {self.info.username}@{self.info.hostname}",
                        markup=False,
                    )
                if self.info.realname:
                    yield Label(f"Name: {self.info.realname}", markup=False)
                if self.info.account:
                    yield Label(f"Account: {self.info.account}", markup=False)
                if self.info.server:
                    server = self.info.server
                    if self.info.server_info:
                        server = f"{server} — {self.info.server_info}"
                    yield Label(f"Server: {server}", markup=False)
                if self.info.channels:
                    yield Label(
                        f"Channels: {' '.join(self.info.channels)}",
                        markup=False,
                    )
                if self.info.idle_seconds is not None:
                    yield Label(
                        f"Idle: {self._format_idle(self.info.idle_seconds)}",
                        markup=False,
                    )

            with Horizontal(id="whois-actions"):
                if not self.info.error:
                    yield Button("Private message", id="message")
                yield Button("Close", id="close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "message":
            self.app.open_private_message(self.info.nickname)
        self.dismiss(None)
