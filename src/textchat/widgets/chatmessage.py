"""Message widgets with lightweight IRC-specific interactions."""
from textchat.screens.private_message import PrivateMessageScreen
from textual import events
from textual.widgets import Label


class ChatMessage(Label):
    """A chat line whose sender link opens the private-message prompt."""

    def on_click(self, event: events.Click) -> None:
        link = event.style.link
        if link is None or not link.startswith("pm:"):
            return

        nickname = link.removeprefix("pm:")
        if not nickname:
            return

        event.prevent_default()
        event.stop()
        self.app.push_screen(PrivateMessageScreen(nickname))
