import asyncio
from datetime import datetime
from pathlib import Path
import time

from textchat.widgets.channeltree import ChannelTree
from textchat.widgets.input import ChatInput
from textchat.screens.quit import QuitScreen
from textchat.db.db import ChannelOperations
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
 
    MODES = {
         "irc" : IRCScreen,
         "settings": SettingsScreen,
         "quit": QuitScreen
    }


    async def on_mount(self) -> None:
        await create_table()
        self.channel_list = None
        self.users = set()
        self.node_list = {}
        self.action_list = ["/join", "/part", "/msg", "/whois"]
        self.channel_ops = ChannelOperations()
        self.username = await self.channel_ops.get_username()
        self.port = await self.channel_ops.get_port()
        self.server_address = await self.channel_ops.get_server_address()
        self.password = await self.channel_ops.get_password()
        self.sasl_login = await self.channel_ops.get_sasl()
        self.irc_screen = self.SCREENS['irc']

        existing_channels = await load_channels()
        if not existing_channels:
             self.app.switch_mode('settings')
        else:
            self.app.push_screen('irc')
            self.irc_client = IRCApp(self,
                                 server_list=[(self.server_address, self.port)],
                                 nickname=self.username,
                                 realname=self.username,
                                 ident_password=self.password,
                                 channels=existing_channels,
                                 sasl_login=self.sasl_login
                                 )

            self.irc_client.start_event_loop()

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.dark = not self.dark

    def action_request_quit(self) -> None:

        def check_quit(quit: bool) -> None:
            if quit:
                try:
                    self.app.irc_client.stop()
                except AttributeError:
                    pass

                self.app.exit()
                
        self.push_screen(QuitScreen(), check_quit) 
    
    def action_open_settings(self) -> None:
        self.push_screen(SettingsScreen()) 


    async def action_return_home(self) -> None: 
        channels = await load_channels()   
        self.username = await self.channel_ops.get_username()
        self.port = await self.channel_ops.get_port()
        self.server_address = await self.channel_ops.get_server_address()
        self.password = await self.channel_ops.get_password()
        self.sasl_login = await self.channel_ops.get_sasl()
        for channel in channels:
            try:
                self.SCREENS['irc'].query_one(TabbedContent).add_pane(TabPane(channel,
                                                        Label(),
                                                       name=channel, 
                                                       id=f'{channel.replace("#", "").lower()}'))
            except:
                self.push_screen(self.SCREENS['irc'])
        try:
            self.irc_client = IRCApp(self,
                                 server_list=[(self.server_address, self.port)],
                                 nickname=self.username,
                                 realname=self.username,
                                 ident_password=self.password,
                                 channels=channels,
                                 sasl_login=self.sasl_login
                                 )

            self.irc_client.start_event_loop()
        except Exception as e:
            print(e)

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
            try:
                self.tab = self.query_one(TabbedContent).active_pane
                now = datetime.now()
                if now.minute <= 9 and event.value.split()[0] not in self.action_list:
                        self.irc_client.connection.privmsg(self.tab.name.replace("@","").replace("+", ""), event.value)
                        self.tab.mount(Label(f'{now.hour}:0{now.minute} <{self.irc_client.nickname}> {event.value}'))
                elif now.minute > 9 and event.value.split()[0] not in self.action_list:
                    self.irc_client.connection.privmsg(self.tab.name.replace("@", "").replace("+", ""), event.value)
                    self.tab.mount(Label(f'{now.hour}:{now.minute} <{self.irc_client.nickname}> {event.value}'))
                elif event.value.split()[0] in self.action_list:
                    if event.value.split()[0] == "/join":
                        await self.irc_client._intercept_join(event.value)
                    elif event.value.split()[0] == "/part":
                        await self.irc_client._intercept_part(event.value)
                    elif event.value.split()[0] == "/whois":
                        await self.irc_client._intercept_whois(event.value)
            

            except NoMatches:
                pass
                 
    def get_channel_list(self):
        if self.app.channel_list is None:
            return None
        else:
            return self.app.channel_list   


    def whois(self, nick):
        self.irc_client.connection.whois(nick)
         
    def irc_message(self, time, channel, sender, message, classes):
        self.tab = self.app.query_one(TabbedContent).get_pane(channel.replace("#", "").lower())
        if self.irc_client.nickname in message:
            self.app.notify(f"{time} <{sender}> {message}", title=channel)
            self.tab.mount(Label(f"{time} <{sender}> {message}", classes="highlight"))
        else:
            self.tab.mount(Label(f'{time} <{sender}> {message}', classes=classes))


    def received_private_message(self, time, sender, message, classes):
        try:
            self.tab = self.app.query_one(TabbedContent).get_pane(f'{sender}')
            self.tab.mount(Label(f'{time} <{sender}> {message}', classes=classes))
            self.active_pane = self.app.query_one(TabbedContent).active_pane
            if self.active_pane == self.tab:
                pass
            else:
                self.notify(f'<{sender}> {message}', title="Private Message")
          
        except:
            self.tab = self.app.query_one(TabbedContent).add_pane(TabPane(sender,
                                                        Label(),
                                                       name=sender, 
                                                       id=f'{sender}'))
            self.tab = self.app.query_one(TabbedContent).get_pane(f'{sender}')
            self.tab.mount(Label(f'{time} <{sender}> {message}', classes=classes))
            self.notify(f'<{sender}> {message}', title="Private Message")
              

    def add_to_tree(self, channel, user_list):
        tree = self.app.query_one(ChannelTree)
        self.app.channel_list = self.app.get_channel_list()
        self.app.channel_ops = ChannelOperations()
        if self.app.channel_list is not None and channel != self.app.channel_list.data['id']:
                channels_list = tree.root.add(channel, data={"id": channel})
                self.app.channel_list = channels_list
                self.app.node_list[channel] = channels_list
        elif self.channel_list is None:
                channels_list = tree.root.add(channel, data={"id": channel})
                self.app.channel_list = channels_list
                self.app.node_list[channel] = channels_list
        else:
            try:
                self.remove_from_tree(channel)
            except:
                pass
            channels_list = tree.root.add(channel, data={"id": channel})
            self.app.channel_list = channels_list
            self.app.node_list[channel] = channels_list
        for user in user_list:
            self.app.channel_list.add_leaf(user, data={"id": user})
        for user in user_list:
             self.app.users.add(user)
        else:
            pass

    def remove_from_tree(self, channel):
        node = self.app.node_list[channel]
        node.remove()
        
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


def main():
    app = TextChat()
    app.run()


if __name__ == "__main__":
    main()