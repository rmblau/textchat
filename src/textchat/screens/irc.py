from textchat.widgets.channeltree import ChannelTree
from textchat.widgets.input import ChatInput
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer
from textual.widgets import TabbedContent


class IRCScreen(Screen):
    def compose(self) -> ComposeResult:
        with TabbedContent():
            pass

        tree: ChannelTree[dict] = ChannelTree("Channels", id="sidebar")
        yield tree
        yield ChatInput(id="chat-input")
        yield Footer()
