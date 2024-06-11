import asyncio
from concurrent.futures import ThreadPoolExecutor
import sys
import threading
from textual import work
from textual.widgets import Label, TabbedContent, TabPane
from irc.client import SimpleIRCClient
from datetime import datetime
import time
from .utils.channels import load_channels
from .db.db import add_channel_to_list

#channels = load_channels()

  

class IRCApp(SimpleIRCClient):
    def __init__(self,app, server_list, nickname, realname, ident_password=None, channels=load_channels()):
        super().__init__()
        self.app = app
        self.server_list = server_list
        self.server_name = server_list[0][0]
        self.server_port = server_list[0][1]
        self.nickname = nickname
        self.realname= realname
        self.ident_password = ident_password
        self.channels = channels
        self._thread_pool = ThreadPoolExecutor(max_workers=1)

    def start_event_loop(self):
        print("connecting..")
        self._thread_pool.submit(self._irc_event_loop)
        print("actually connecting")

    def _irc_event_loop(self):
        self.start() 
        print("really connecting!!!!")
    def stop(self):
        self._thread_pool.shutdown(wait=False)

    
    def start(self):
        self.connect(
                    self.server_name,
                    self.server_port,
                    self.nickname,
                    self.ident_password,
                    self.realname,
                   )
        super().start()
    
    def on_welcome(self, connection, event):
        #self.connection.privmsg("nickserv", f'identify {self.password}')
        for channel in self.channels:
            connection.join(channel)
            #await add_channel_to_list(channel)
        time.sleep(7)
        self.app.notify("Connected!")

    
    async def _intercept_join(self, message):
        self.tab = self.app.query_one(TabbedContent).active_pane 
        if message.startswith("/join"):
            channel = message.split()[1]
            if not channel in self.channels:
                self.connection.join(channel) 
                self.channels.append(channel)
                await add_channel_to_list(channel)
                self.app.query_one(TabbedContent).add_pane(TabPane(channel,
                                                        Label(),
                                                       name=channel, 
                                                       id=f'{channel.replace("#", "").lower()}'))
            else:
                self.app.notify(f"Already in {channel}!")
            return True
        return False 
    
    def _intercept_part(self, message):
        self.tab = self.app.query_one(TabbedContent).active_pane 
        if message.startswith("/part"):
            channel = message.split()[1]
            self.connection.part(channel) 
            self.channels.remove(channel)
            self.app.query_one(TabbedContent).remove_pane(f'{channel.replace("#", "").lower()}')
            return True
        return False 
    
    def on_pubmsg(self, connection, event):
        print(event)
        sender = event.source.nick
        message = event.arguments[0]
        channel = event.target
        now = datetime.now()
        if now.minute <= 9:
            self.app.handle_irc_message(f'{now.hour}:0{now.minute}', channel,  sender, message, classes=None)
        else:
            self.app.handle_irc_message(f'{now.hour}:{now.minute}', channel,  f'{sender}', message, classes=None)

    def on_privmsg(self, connection, event):
        message = event.arguments[0]
        user = event.source.nick
        now = datetime.now()
        if now.minute <= 9:
            self.app.handle_private_message(f'{now.hour}:0{now.minute}',  user, message, classes=None)
        else:
            self.app.handle_private_message(f'{now.hour}:{now.minute}', user, message, classes=None)

    def on_ctcp(self, connection, event):
        sender = event.source.nick
        message = event.arguments[1]
        channel = event.target
        now = datetime.now()
        classes = "italics"
        if now.minute  <= 9:

            self.app.handle_irc_message(f'{now.hour}:0{now.minute}', channel,  f'{sender}', message, classes)
        else:
            self.app.handle_irc_message(f'{now.hour}:{now.minute}', channel,  f'{sender}', message, classes)

    def on_namreply(self, connection, event):
        channel = event.arguments[1]
        user_list = event.arguments[2].split()
        self.app.add_to_tree(channel, user_list)

    def on_join(self, connection, event):
        sender = event.source.nick
        try:
            message = event.arguments[0]
        except IndexError:
            message = "has joined"
        channel = event.target
        now = datetime.now()
        classes = "italics"
        if now.minute  <= 9 and self.nickname != sender:
            self.app.handle_irc_message(f'{now.hour}:0{now.minute}', channel,  f'{sender}', message, classes)
        elif self.nickname != sender:
            self.app.handle_irc_message(f'{now.hour}:{now.minute}', channel,  f'{sender}', message, classes)
    
    def on_disconnect(self):
        self._stop_event.set()


