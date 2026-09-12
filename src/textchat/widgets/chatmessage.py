"""Message widgets with lightweight IRC-specific interactions."""
from textchat.screens.private_message import PrivateMessageScreen
from textual import events
from textual.widgets import Label


class ChatMessage(Label):
    """A chat line whose sender opens the private-message prompt."""

    def on_click(self, event: events.Click) -> None:
        metadata = event.style.meta or {}
        nickname = metadata.get("pm")
        if not isinstance(nickname, str) or not nickname:
            return

        event.prevent_default()
        event.stop()
        self.app.push_screen(PrivateMessageScreen(nickname))
