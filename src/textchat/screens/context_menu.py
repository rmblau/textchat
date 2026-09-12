from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button
from textual.widgets import Label


@dataclass(frozen=True)
class ContextTarget:
    """The IRC object a context menu action applies to."""

    kind: str
    value: str


class ContextMenu(ModalScreen[str | None]):
    """A small in-terminal context menu for users and channels."""

    def __init__(self, target: ContextTarget) -> None:
        super().__init__()
        self.target = target

    def compose(self) -> ComposeResult:
        with Vertical(id="context-menu"):
            yield Label(self.target.value, id="context-title", markup=False)

            if self.target.kind == "user":
                yield Button("Private message", id="message")
                yield Button("WHOIS", id="whois")
            else:
                yield Button("Open tab", id="open")
                yield Button("Close tab", id="close")
                yield Button("Part channel", id="part", variant="error")

            yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = None if event.button.id == "cancel" else event.button.id
        self.dismiss(action)
