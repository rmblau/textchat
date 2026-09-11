from textual import events
from textual.widgets import Input


class ChatInput(Input):
    async def _on_key(self, event: events.Key) -> None:
        if event.key == "tab" and self.app.complete_nickname(self):
            event.prevent_default()
            event.stop()
            return

        await super()._on_key(event)
