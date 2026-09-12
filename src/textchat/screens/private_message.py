from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button
from textual.widgets import Label


class PrivateMessageScreen(ModalScreen[None]):
    """Confirm opening a private-message tab for one IRC user."""

    def __init__(self, nickname: str) -> None:
        super().__init__()
        self.nickname = nickname.lstrip("@+%&~")

    def compose(self) -> ComposeResult:
        with Vertical(id="private-message-dialog"):
            yield Label(
                f"Start a private message with {self.nickname}?",
                id="private-message-title",
                markup=False,
            )
            with Horizontal(id="private-message-actions"):
                yield Button("Private message", id="message")
                yield Button("Cancel", id="cancel", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "message":
            self.app.open_private_message(self.nickname)
        self.dismiss(None)
