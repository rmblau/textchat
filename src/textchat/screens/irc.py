import asyncio
from textchat.screens.quit import QuitScreen
from textchat.utils.channels import load_channels
from textchat.widgets.input import ChatInput
from textchat.widgets.channeltree import ChannelTree
from textchat.widgets.channel_list import ChannelContainer
from textual.app import ComposeResult
from textual.widgets import Footer, TabbedContent,TabPane, Label

from textual.screen import Screen
from textual_autocomplete import AutoComplete, Dropdown, DropdownItem, InputState


class IRCScreen(Screen):
    try:
        channels = asyncio.run(load_channels())
    except:
        channels = False
    def compose(self) -> ComposeResult:
        def get_items(input_state: InputState):
            items = []
            for user in self.app.users:
                items.append(
                    DropdownItem(user.replace("+", "").replace("@", ""))
                )
            matches = sorted([c for c in items if input_state.value.lower() in c.main.plain.lower()])
            return matches
        
        with TabbedContent():
            if self.channels:
                for name in self.channels:
                    tab_id = f'{name.replace("#", "")}'
                    with TabPane(name, name=name, id=tab_id.lower()):
                        yield(Label())
            else:
                pass
        tree: ChannelTree[dict] = ChannelTree("Channels", id="sidebar")
        yield tree
        yield ChatInput(id="chat-input")
        #yield AutoComplete(ChatInput(placeholder=f"Enter your message", id="chat-input"), Dropdown(items=get_items))
        yield Footer()
