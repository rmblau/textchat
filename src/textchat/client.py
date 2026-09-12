import functools
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime

import irc
from irc.client import SimpleIRCClient

from .db.db import ChannelOperations


@dataclass
class WhoisInfo:
    """Information returned by one IRC WHOIS response."""

    nickname: str
    username: str | None = None
    hostname: str | None = None
    realname: str | None = None
    server: str | None = None
    server_info: str | None = None
    account: str | None = None
    channels: list[str] = field(default_factory=list)
    idle_seconds: int | None = None
    error: str | None = None


class IRCApp(SimpleIRCClient):
    def __init__(
        self,
        app,
        server_list,
        nickname,
        realname,
        ident_password=None,
        znc_username=None,
        znc_network=None,
        use_tls=False,
        channels=None,
        sasl_login=None,
    ):
        super().__init__()

        self.app = app
        self.server_list = server_list
        self.server_name = server_list[0][0]
        self.server_port = int(server_list[0][1])

        self.nickname = nickname
        self.realname = realname
        self.ident_password = ident_password

        # Optional ZNC connection settings.
        self.znc_username = znc_username
        self.znc_network = znc_network
        self.use_tls = use_tls

        self.channels = channels if channels is not None else []
        self.sasl_login = sasl_login

        self._thread_pool = ThreadPoolExecutor(max_workers=1)
        self._running = False
        self._stopping = False
        self.channel_users = {}
        self.channel_names = {}
        self._names_in_progress = set()
        self._whois_requests = {}

    @staticmethod
    def _channel_key(channel):
        return channel.casefold()

    @staticmethod
    def _nickname_key(nickname):
        return nickname.lstrip("@+%&~").casefold()

    def _publish_channel_users(self, channel):
        """Refresh the UI with members belonging to just this channel."""
        channel_key = self._channel_key(channel)
        self.app.update_channel_tree(
            self.channel_names.get(channel_key, channel),
            self.channel_users.get(channel_key, set()).copy(),
        )

    def _remove_user_from_channel(self, channel, nickname):
        channel_key = self._channel_key(channel)
        users = self.channel_users.get(channel_key)
        if users is None:
            return

        nickname_key = self._nickname_key(nickname)
        self.channel_users[channel_key] = {
            user for user in users if self._nickname_key(user) != nickname_key
        }
        self._publish_channel_users(channel)

    def start_event_loop(self):
        if self._running:
            return

        self._running = True
        self._stopping = False
        self._thread_pool.submit(self._irc_event_loop)

    def _irc_event_loop(self):
        try:
            self.start()
        finally:
            self._running = False

    def stop(self):
        """Disconnect the IRC socket and let the reactor thread exit."""
        if self._stopping:
            return

        self._stopping = True
        self._running = False

        try:
            if self.connection.is_connected():
                self.connection.disconnect("Textchat exiting")
        finally:
            self._thread_pool.shutdown(wait=False, cancel_futures=True)

    def start(self):
        # Normal IRC: username is the nickname.
        # ZNC: username becomes "znc-user/network".
        username = self.znc_username or self.nickname
        if self.znc_username and self.znc_network:
            username = f"{self.znc_username}/{self.znc_network}"

        options = {
            "server": self.server_name,
            "port": self.server_port,
            "nickname": self.nickname,
            "username": username,
            "ircname": self.realname,
            "password": self.ident_password,
        }

        # TLS is independent of SASL and port number.
        if self.use_tls:
            context = ssl.create_default_context()
            options["connect_factory"] = irc.connection.Factory(
                wrapper=functools.partial(
                    context.wrap_socket,
                    server_hostname=self.server_name,
                )
            )

        # Leave this false for ordinary ZNC PASS authentication.
        # When enabled, python-irc uses the password for SASL instead of PASS.
        if self.sasl_login:
            options["sasl_login"] = username

        self.connect(**options)
        while self._running:
            self.reactor.process_once(timeout=0.2)

    def on_welcome(self, connection, event):
        candidates = (
            getattr(event, "target", None),
            connection.get_nickname(),
        )
        for candidate in candidates:
            if candidate and not any(char.isspace() for char in candidate):
                self.nickname = candidate
                break
        else:
            welcome = connection.get_nickname() or ""
            if welcome.startswith("Welcome to "):
                self.nickname = welcome.rsplit(maxsplit=1)[-1]

        for channel in self.channels:
            connection.join(channel)

        time.sleep(7)
        self.app.notify("Connected!")

    async def _intercept_join(self, message):
        if message.startswith("/join"):
            channel = message.split()[1]

            if channel not in self.channels:
                self.connection.join(channel)
                self.channels.append(channel)

                channel_ops = ChannelOperations()
                await channel_ops.add_channel_to_list(channel)
                await self.app._ensure_channel_tab(channel)
            else:
                self.app.notify(f"Already in {channel}!")

            return True

        return False

    def request_whois(self, nickname):
        """Request WHOIS data and retain the response until it is complete."""
        nickname = nickname.lstrip("@+%&~")
        if not nickname:
            return

        self._whois_requests[nickname.casefold()] = WhoisInfo(nickname=nickname)
        self.connection.whois(nickname)

    def _whois_info(self, event):
        if not event.arguments:
            return None

        return self._whois_requests.get(event.arguments[0].casefold())

    def on_whoisuser(self, connection, event):
        # RPL_WHOISUSER: <nick> <username> <host> * :<real name>
        info = self._whois_info(event)
        if info is not None and len(event.arguments) >= 5:
            info.username = event.arguments[1]
            info.hostname = event.arguments[2]
            info.realname = event.arguments[4]

    def on_whoisserver(self, connection, event):
        # RPL_WHOISSERVER: <nick> <server> :<server description>
        info = self._whois_info(event)
        if info is not None and len(event.arguments) >= 3:
            info.server = event.arguments[1]
            info.server_info = event.arguments[2]

    def on_whoischannels(self, connection, event):
        info = self._whois_info(event)
        if info is not None and len(event.arguments) >= 2:
            info.channels = event.arguments[1].split()

    def on_whoisidle(self, connection, event):
        info = self._whois_info(event)
        if info is not None and len(event.arguments) >= 2:
            try:
                info.idle_seconds = int(event.arguments[1])
            except ValueError:
                pass

    def on_whoisaccount(self, connection, event):
        info = self._whois_info(event)
        if info is not None and len(event.arguments) >= 2:
            info.account = event.arguments[1]

    def on_nosuchnick(self, connection, event):
        info = self._whois_info(event)
        if info is None:
            return

        info.error = event.arguments[-1] if len(event.arguments) > 1 else "No such nick"
        self._whois_requests.pop(info.nickname.casefold(), None)
        self.app.handle_whois_result(info)

    def on_endofwhois(self, connection, event):
        info = self._whois_info(event)
        if info is None:
            return

        self._whois_requests.pop(info.nickname.casefold(), None)
        self.app.handle_whois_result(info)

    async def _intercept_whois(self, message):
        command, _, nickname = message.partition(" ")
        if command != "/whois":
            return False

        if not nickname.strip():
            self.app.notify("Usage: /whois <nickname>")
            return True

        self.request_whois(nickname.strip())
        return True

    def send_private_message(self, target, message):
        self.connection.privmsg(target, message)

    async def _intercept_part(self, message):
        command, _, channel = message.partition(" ")
        if command != "/part":
            return False

        if not channel.strip():
            self.app.notify("Usage: /part <channel>")
            return True

        await self.part_channel(channel.strip().split(maxsplit=1)[0])
        return True

    async def part_channel(self, channel):
        """Part a channel whether it originated locally or through ZNC."""
        channel_key = self._channel_key(channel)
        self.connection.part(channel)
        if channel in self.channels:
            self.channels.remove(channel)

        # Do this before the server's PART reply arrives. Otherwise the reply
        # can publish the cached member list and recreate the removed node.
        self.channel_users.pop(channel_key, None)
        self.channel_names.pop(channel_key, None)
        self._names_in_progress.discard(channel_key)

        channel_ops = ChannelOperations()
        await channel_ops.delete_channel(channel)
        await self.app._close_channel_tab(channel)
        self.app.remove_from_tree(channel)

    def on_pubmsg(self, connection, event):
        sender = event.source.nick
        message = event.arguments[0]
        channel = event.target
        now = datetime.now()

        if now.minute <= 9:
            self.app.handle_irc_message(
                f"{now.hour}:0{now.minute}",
                channel,
                sender,
                message,
                classes=None,
            )
        else:
            self.app.handle_irc_message(
                f"{now.hour}:{now.minute}",
                channel,
                sender,
                message,
                classes=None,
            )

    def on_privmsg(self, connection, event):
        message = event.arguments[0]
        user = event.source.nick
        now = datetime.now()

        if now.minute <= 9:
            self.app.handle_private_message(
                f"{now.hour}:0{now.minute}",
                user,
                message,
                classes=None,
            )
        else:
            self.app.handle_private_message(
                f"{now.hour}:{now.minute}",
                user,
                message,
                classes=None,
            )

    def on_ctcp(self, connection, event):
        sender = event.source.nick
        message = event.arguments[1]
        channel = event.target
        now = datetime.now()
        classes = "italics"

        if now.minute <= 9:
            self.app.handle_irc_message(
                f"{now.hour}:0{now.minute}",
                channel,
                sender,
                message,
                classes,
            )
        else:
            self.app.handle_irc_message(
                f"{now.hour}:{now.minute}",
                channel,
                sender,
                message,
                classes,
            )

    def on_namreply(self, connection, event):
        channel = event.arguments[1]
        user_list = event.arguments[2].split()
        channel_key = self._channel_key(channel)

        self.app.ensure_channel_tab(channel)

        # A NAMES response can be split across multiple replies. Reset only at
        # the start of a response, then merge the following chunks.
        if channel_key not in self._names_in_progress:
            self.channel_users[channel_key] = set()
            self.channel_names[channel_key] = channel
            self._names_in_progress.add(channel_key)

        self.channel_users[channel_key].update(user_list)

    def on_endofnames(self, connection, event):
        for argument in event.arguments:
            if argument and argument[0] in "#&!+":
                channel_key = self._channel_key(argument)
                self._names_in_progress.discard(channel_key)
                self._publish_channel_users(argument)
                break

    def on_join(self, connection, event):
        sender = event.source.nick

        try:
            message = event.arguments[0]
        except IndexError:
            message = "has joined"

        channel = event.target
        channel_key = self._channel_key(channel)
        now = datetime.now()
        classes = "italics"

        self.app.ensure_channel_tab(channel)

        self.channel_names[channel_key] = channel
        self.channel_users.setdefault(channel_key, set()).add(sender)
        self._publish_channel_users(channel)

        if now.minute <= 9 and self.nickname != sender:
            self.app.handle_irc_message(
                f"{now.hour}:0{now.minute}",
                channel,
                sender,
                message,
                classes,
                mark_unread=False,
            )
        elif self.nickname != sender:
            self.app.handle_irc_message(
                f"{now.hour}:{now.minute}",
                channel,
                sender,
                message,
                classes,
                mark_unread=False,
            )

    def on_part(self, connection, event):
        self._remove_user_from_channel(event.target, event.source.nick)

    def on_quit(self, connection, event):
        nickname = event.source.nick
        for channel_key, channel in tuple(self.channel_names.items()):
            if channel_key in self.channel_users:
                self._remove_user_from_channel(channel, nickname)

    def on_disconnect(self, connection, event):
        self.stop()
