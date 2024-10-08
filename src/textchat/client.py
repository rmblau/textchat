from concurrent.futures import ThreadPoolExecutor
from textual.widgets import Label, TabbedContent, TabPane, Tree
from irc.client import SimpleIRCClient
import irc
from datetime import datetime
import time
import ssl
import functools

from .utils.channels import load_channels
from .db.db import ChannelOperations

class IRCApp(SimpleIRCClient):
    def __init__(self,
                 app, 
                 server_list, 
                 nickname, 
                 realname, 
                 ident_password=None, 
                 channels=load_channels(),
                 sasl_login=None
    ):
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
        self.sasl_login = sasl_login
        self.user_list = set()
        self.user_info = None

    def start_event_loop(self):
        self._thread_pool.submit(self._irc_event_loop)

    def _irc_event_loop(self):
        try:
            self.start() 
        except KeyboardInterrupt:
            self.stop()


    def stop(self):
        self._thread_pool.shutdown(wait=False, cancel_futures=True)
        self.quit()

    
    def start(self):
        if self.sasl_login and self.server_port == 6697:
            context = ssl.create_default_context()
            wrapper = functools.partial(context.wrap_socket, server_hostname=self.server_name)

            self.connect(
                    server=self.server_name,
                    port=self.server_port,
                    nickname=self.nickname,
                    password=self.ident_password,
                    sasl_login=self.nickname,
                    connect_factory=irc.connection.Factory(wrapper=wrapper)
                )
        elif self.sasl_login:
            self.connect(
                    server=self.server_name,
                    port=self.server_port,
                    nickname=self.nickname,
                    password=self.ident_password,
                    sasl_login=self.nickname
            )
        else:
             self.connect(
                    server=self.server_name,
                    port=self.server_port,
                    nickname=self.nickname,
                    password=self.ident_password
             )
            
        super().start()
    
    def on_welcome(self, connection, event):
        for channel in self.channels:
            connection.join(channel)
        time.sleep(7)
        self.app.notify("Connected!")

    
    async def _intercept_join(self, message):
        self.tab = self.app.query_one(TabbedContent).active_pane 
        if message.startswith("/join"):
            channel = message.split()[1]
            if not channel in self.channels:
                self.connection.join(channel) 
                self.channels.append(channel)
                channel_ops = ChannelOperations()
                await channel_ops.add_channel_to_list(channel)
                self.app.query_one(TabbedContent).add_pane(TabPane(channel,
                                                        Label(),
                                                       name=channel, 
                                                       id=f'{channel.replace("#", "").lower()}'))
           
            else:
                self.app.notify(f"Already in {channel}!")
            return True
        return False
    
    async def _intercept_whois(self, message):
        self.tab = self.app.query_one(TabbedContent).active_pane 
        if message.startswith("/whois"):
            user = message.split()[1]
            self.user_info = self.app.whois(user)
            print(f'{self.user_info=}')
            return True
        return False
    
    def on_whois(self, connection, event):
        print(f'{event.arguments[1]=}')

    def send_private_message(self, target, message):
        self.connection.privmsg(target, message)

      
    async def _intercept_part(self, message):
        self.tab = self.app.query_one(TabbedContent).active_pane 
        if message.startswith("/part"):
            channel = message.split()[1]
            self.connection.part(channel) 
            self.channels.remove(channel)
            channel_ops = ChannelOperations()
            await channel_ops.delete_channel(channel)
            self.app.query_one(TabbedContent).remove_pane(f'{channel.replace("#", "").lower()}')
            self.app.remove_from_tree(channel)
            return True
        return False 
    
    def on_pubmsg(self, connection, event):
        sender = event.source.nick
        message = event.arguments[0]
        channel = event.target
        now = datetime.now()
        user = connection.whois(sender)
        if now.minute <= 9:
            self.app.handle_irc_message(f'{now.hour}:0{now.minute}', channel,  sender, message, classes=None)
        else:
            self.app.handle_irc_message(f'{now.hour}:{now.minute}', channel,  f'{sender}', message, classes=None)

    def on_privmsg(self, connection, event):
        message = event.arguments[0]
        user = event.source.nick
        print(f'{user=}')
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
        for user in user_list:
            self.user_list.add(user)
        self.app.add_to_tree(channel, self.user_list)

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
        self.stop()


