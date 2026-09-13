from textchat.widgets.channeltree import ChannelTree
from textchat.widgets.input import ChatInput
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
            with TabbedContent():
                pass

            with Vertical(id="sidebar-column"):
                yield ChannelTree("Channels", id="sidebar")
        yield ChatInput(id="chat-input")
        yield Footer()

    async def on_mount(self) -> None:
        """Dock the optional topic bar beneath TabbedContent's tab strip."""
        tabbed = self.query_one(TabbedContent)
        await tabbed.mount(
            Collapsible(
                Static("No channel selected", id="topic-bar", markup=False),
                title="Topic",
                collapsed=False,
                id="topic-container",
            )
        )
