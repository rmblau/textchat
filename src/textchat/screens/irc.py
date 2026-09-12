from textchat.widgets.channeltree import ChannelTree
from textchat.widgets.input import ChatInput
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer
from textual.widgets import TabbedContent


class IRCScreen(Screen):
    def compose(self) -> ComposeResult:
        with Horizontal(id="chat-layout"):
            with TabbedContent():
                pass

            yield ChannelTree("Channels", id="sidebar")
        yield ChatInput(id="chat-input")
        yield Footer()
