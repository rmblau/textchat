from textual.app import ComposeResult
from textual.containers import Grid
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Button
from textual.widgets import Label
from textual.widgets import TabbedContent
from textual.widgets import TabPane


class WhoisScreen(ModalScreen[bool]):
    def compose(self) -> ComposeResult:
        yield Grid(
            Label("Sent PM to this user?", id="question"),
            Button("Private Message", variant="error", id="message"),
            Button("Cancel", variant="primary", id="cancel"),
            id="dialog",
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "message":
            user = self.app.user.replace("@", "").replace("+", "")
            tabbed_content = self.app.get_screen("irc").query_one(TabbedContent)

            try:
                tabbed_content.get_pane(user)
            except NoMatches:
                await tabbed_content.add_pane(
                    TabPane(user, Label(), name=user, id=user)
                )

            tabbed_content.active = user

            self.dismiss(True)
        else:
            self.dismiss(False)
