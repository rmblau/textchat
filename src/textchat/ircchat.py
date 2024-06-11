from datetime import datetime
from pathlib import Path

from textchat.widgets.input import ChatInput

from textchat.screens.quit import QuitScreen
from textchat.db.db import get_password, get_port, get_server_address, get_username
from textual import work
from textual import on
from textual.app import App
from textual.widgets import Label, TabbedContent, TabPane,Tree
from textual.worker import get_current_worker
from textual.css.query import NoMatches

from textchat.client import IRCApp
from textchat.screens.irc import IRCScreen
from textchat.screens.settings import SettingsScreen
from textchat.db.base import create_table
from textchat.utils.channels import load_channels


class TextChat(App):
    def __init__(self):
        super().__init__()
    CSS_PATH = Path('irc.tcss')
    SCREENS = {"irc": IRCScreen(), "settings":SettingsScreen() }
    BINDINGS = [("ctrl+h", "return_home", "Home"),
                ("ctrl+s", "open_settings", "Settings"),
                ("ctrl+q", "request_quit", "Quit"), 
                ("ctrl+d", "toggle_dark", "Toggle dark mode")
                ]
 


    async def on_mount(self) -> None:
        await create_table()
        self.channel_list = None
        self.users = set()
        self.username = await get_username()
        self.port = await get_port()
        self.server_address = await get_server_address()
        self.password = await get_password()

        existing_channels = await load_channels()
        if not existing_channels:
             self.app.push_screen(self.SCREENS['settings'])
        else:
            self.app.push_screen(self.SCREENS['irc'])
            self.irc_client = IRCApp(self,
                                 server_list=[(self.server_address, self.port)],
                                 nickname=self.username,
                                 realname=self.username,
                                 ident_password=self.password,
                                 channels=existing_channels,
                                 )
            self.irc_client.start_event_loop()

             
    
    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.dark = not self.dark

    def action_request_quit(self) -> None:

        def check_quit(quit: bool) -> None:
            if quit:
                self.irc_client.stop()

                self.app.exit()
                
        self.push_screen(QuitScreen(), check_quit) 
    
    def action_open_settings(self) -> None:
        self.push_screen(SettingsScreen()) 

    def action_return_home(self) -> None:
         self.push_screen(self.SCREENS['irc'])
          
    @on(ChatInput.Submitted) 
    async def send_message(self, event) -> None:
        try:
             
            input = self.query_one(ChatInput)
        except NoMatches:
             input = False
        if not input:
             pass
        else:
            input.value = "" 
            self.tab = self.query_one(TabbedContent).active_pane
            now = datetime.now()
            if now.minute <= 9 and not await self.irc_client._intercept_join(event.value):
                    self.irc_client.connection.privmsg(self.tab.name, event.value)
                    self.tab.mount(Label(f'{now.hour}:0{now.minute} <{self.irc_client.nickname}> {event.value}'))
            elif not await self.irc_client._intercept_join(event.value):
                self.irc_client.connection.privmsg(self.tab.name, event.value)
                self.tab.mount(Label(f'{now.hour}:{now.minute} <{self.irc_client.nickname}> {event.value}'))

    def get_channel_list(self):
        if self.app.channel_list is None:
            return None
        else:
            return self.app.channel_list    
         
    def irc_message(self, time, channel, sender, message,classes):
        self.tab = self.app.query_one(TabbedContent).get_pane(channel.replace("#", "").lower())
        if self.irc_client.nickname in message:
            self.app.notify(f"{time} <{sender}> {message}", title=channel)
            self.tab.mount(Label(f"{time} <{sender}> {message}", classes="highlight"))
        else:
            self.tab.mount(Label(f'{time} <{sender}> {message}', classes=classes))


    def received_private_message(self, time, sender, message, classes):
        self.tab = self.app.query_one(TabbedContent).add_pane(TabPane(sender,
                                                        Label(),
                                                       name=sender, 
                                                       id=f'{sender}'))
        self.tab = self.app.query_one(TabbedContent).get_pane(f'{sender}')
        self.tab.mount(Label(f'{time} <{sender}> {message}', classes=classes))


    def add_to_tree(self, channel, user_list):
        tree = self.app.query_one(Tree)
        self.app.channel_list = self.app.get_channel_list()
        if self.app.channel_list is not None and channel != self.app.channel_list.data:
                channels_list = tree.root.add(channel, data=channel)
                self.app.channel_list = channels_list
        elif self.channel_list is None:
                channels_list = tree.root.add(channel, data=channel)
                self.app.channel_list = channels_list
        for user in user_list:
                self.app.channel_list.add_leaf(user)
        for user in user_list:
             self.app.users.add(user)
        else:
            pass
        
    @work(exclusive=True)
    async def handle_irc_message(self, time, channel, sender, message, classes):
        worker = get_current_worker()
        if not worker.is_cancelled:
            self.irc_message(time, channel, sender, message, classes) 
        else:
            pass
    
    @work(exclusive=True)
    async def handle_private_message(self, time, sender, message, classes):
        worker = get_current_worker()
        if not worker.is_cancelled:
            self.received_private_message(time, sender, message, classes) 
        else:
            pass
    async def on_shutdown(self):
        self.irc_client.on_disconnect() 

app = TextChat()
app.run()
