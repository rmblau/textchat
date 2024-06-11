import asyncio
from textchat.utils.channels import load_channels
from textchat.widgets.input import ChatInput
from textual.app import ComposeResult
from textual.widgets import Tree, Footer, TabbedContent, TabPane, Label
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
            matches = [c for c in items if input_state.value.lower() in c.main.plain.lower()]
            ordered = sorted(matches, key=lambda v: input_state.value.lower() in v.main.plain.lower(), reverse=True)
            return ordered


        with TabbedContent() as self.tabbed_content:
            if not self.channels:
                with TabPane("uh oh!"):
                    yield(Label("Please visit the settings tab and restart when finished to see your channels here!"))
            else:
                for name in self.channels:
                    tab_id = f'{name.replace("#", "")}'
                    with TabPane(name, name=name, id=tab_id.lower()):
                        yield(Label())
        tree: Tree[dict] = Tree("Channels", id="sidebar")
        yield tree
        yield ChatInput(id="chat-input")
        #yield AutoComplete(ChatInput(placeholder=f"Enter your message", id="chat-input"), Dropdown(items=get_items))
        yield Footer()
