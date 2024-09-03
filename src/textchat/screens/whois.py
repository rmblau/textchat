from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, Label, TabbedContent, TabPane

class WhoisScreen(ModalScreen[bool]):
    def compose(self) -> ComposeResult:
        yield Grid(
            Label(f"Sent PM to this user?", id="question"),
            Button("Private Message", variant="error", id="message"),
            Button("Cancel", variant="primary", id="cancel"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "message":
            try:
                self.tab = self.app.irc_screen().query_one(TabbedContent).get_pane(f'{self.app.user.replace("@", "").replace("+", "")}')
                    
            except:
                self.active_tab = self.app.SCREENS['irc'].query_one(TabbedContent).add_pane(TabPane(self.app.user.replace("@", "").replace("+", ""), 
                                                                              Label(),
                                                                              name=self.app.user.replace("@", "").replace("+", ""), 
                                                                              id=f'{self.app.user.replace("@", "").replace("+", "")}'))
            self.dismiss(True)
            
        else:

            self.dismiss(False)