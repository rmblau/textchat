from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button
from textual.widgets import Label


class KickedScreen(ModalScreen[bool]):
    """Offer to rejoin a channel after the local user is kicked."""

    def __init__(self, channel: str, kicker: str, reason: str) -> None:
        super().__init__()
        self.channel = channel
        self.kicker = kicker
        self.reason = reason

    def compose(self) -> ComposeResult:
        with Vertical(id="kicked-dialog"):
            yield Label(
                f"You were kicked from ({self.channel})",
                id="kicked-title",
                markup=False,
            )
            details = f"By {self.kicker}"
            if self.reason:
                details += f" — {self.reason}"
            yield Label(details, markup=False)
            with Horizontal(id="kicked-actions"):
                yield Button(f"Rejoin {self.channel}", id="rejoin", variant="primary")
                yield Button("Close", id="dismiss")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "rejoin")
