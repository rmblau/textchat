from textchat.widgets.channeltree import ChannelTree
from textchat.widgets.input import ChatInput
from textchat.widgets.usertree import UserTree
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Collapsible
from textual.widgets import Footer
from textual.widgets import Static
from textual.widgets import TabbedContent


class IRCScreen(Screen):
    def compose(self) -> ComposeResult:
        with Horizontal(id="chat-layout"):
            yield ChannelTree("Channels", id="channel-sidebar")

            with TabbedContent():
                pass

            yield UserTree("Users", id="user-sidebar")
        yield ChatInput(id="chat-input")
        yield Footer()

    async def on_mount(self) -> None:
        """Dock the optional topic bar beneath TabbedContent's tab strip."""
        self.query_one(ChannelTree).root.expand()
        self.query_one(UserTree).root.expand()
        tabbed = self.query_one(TabbedContent)
        await tabbed.mount(
            Collapsible(
                Static("No channel selected", id="topic-bar", markup=False),
                title="Topic",
                collapsed=False,
                id="topic-container",
            )
        )
