import re
from datetime import datetime
from pathlib import Path

from textchat.client import IRCApp
from textchat.db.base import create_table
from textchat.db.db import ChannelOperations
from textchat.screens.irc import IRCScreen
from textchat.screens.quit import QuitScreen
from textchat.screens.settings import SettingsScreen
from textchat.utils.channels import load_channels
from textchat.widgets.channeltree import ChannelTree
from textchat.widgets.input import ChatInput
from textual import on
from textual import work
from textual.app import App
from textual.css.query import NoMatches
from textual.widgets import Label
from textual.widgets import TabbedContent
from textual.widgets import TabPane
from textual.worker import get_current_worker


class TextChat(App):
    CSS_PATH = Path("irc.tcss")

    SCREENS = {
        "irc": IRCScreen,
        "settings": SettingsScreen,
    }

    BINDINGS = [
        ("ctrl+h", "return_home", "Home"),
        ("ctrl+s", "open_settings", "Settings"),
        ("ctrl+q", "request_quit", "Quit"),
        ("ctrl+d", "toggle_dark", "Toggle dark mode"),
    ]

    MODES = {
        "irc": IRCScreen,
        "settings": SettingsScreen,
        "quit": QuitScreen,
    }

    async def on_mount(self) -> None:
        await create_table()

        self.channel_list = None
        self.users = set()
        self.node_list = {}
        self.action_list = ["/join", "/part", "/msg", "/whois"]
        self.channel_ops = ChannelOperations()
        self.irc_screen = self.get_screen("irc", IRCScreen)

        server = await self.channel_ops.get_server_info()
        existing_channels = await load_channels()

        if server is None:
            self.switch_mode("settings")
            return

        await self.push_screen("irc")
        for channel in existing_channels:
            await self._ensure_channel_tab(channel)

        self.irc_client = self._make_irc_client(server, existing_channels)
        self.irc_client.start_event_loop()

    def _make_irc_client(self, server, channels):
        return IRCApp(
            self,
            server_list=[(server.server_address, server.port)],
            nickname=server.nickname,
            realname=server.nickname,
            ident_password=server.password,
            znc_username=server.znc_username,
            znc_network=server.znc_network,
            use_tls=server.use_tls,
            channels=channels,
            sasl_login=server.sasl_login,
        )

    @staticmethod
    def _channel_pane_id(channel):
        return channel.replace("#", "").lower()

    async def _ensure_channel_tab(self, channel):
        """Create a tab when local settings or ZNC expose a channel."""
        channel = channel.strip()
        if not channel:
            return

        tabbed_content = self.get_screen("irc", IRCScreen).query_one(TabbedContent)
        pane_id = self._channel_pane_id(channel)

        try:
            tabbed_content.get_pane(pane_id)
        except Exception:
            await tabbed_content.add_pane(
                TabPane(channel, Label(), name=channel, id=pane_id)
            )

    @work(group="irc-tabs", exit_on_error=False)
    async def ensure_channel_tab(self, channel):
        await self._ensure_channel_tab(channel)

    @work(group="irc-tree", exit_on_error=False)
    async def update_channel_tree(self, channel, user_list):
        await self._ensure_channel_tab(channel)
        self.add_to_tree(channel, user_list)

    def action_toggle_dark(self) -> None:
        self.dark = not self.dark

    def complete_nickname(self, chat_input):
        """Replace the word before the cursor with a known IRC nickname."""
        before_cursor = chat_input.value[: chat_input.cursor_position]
        match = re.search(r"(\S+)$", before_cursor)
        if match is None or match.group(1).startswith("/"):
            return False

        prefix = match.group(1).lstrip("@+%&~")
        if not prefix:
            return False

        candidates = sorted(
            {
                user.lstrip("@+%&~")
                for user in self.users
                if user.lstrip("@+%&~").casefold().startswith(prefix.casefold())
            },
            key=str.casefold,
        )
        if not candidates:
            return False

        nickname = candidates[0]
        suffix = ": " if match.start() == 0 else ""
        replacement = nickname + suffix
        chat_input.value = (
            before_cursor[: match.start()]
            + replacement
            + chat_input.value[chat_input.cursor_position :]
        )
        chat_input.cursor_position = match.start() + len(replacement)
        return True

    def action_request_quit(self) -> None:
        def check_quit(quit: bool) -> None:
            if quit:
                try:
                    self.irc_client.stop()
                except AttributeError:
                    pass

                self.exit()

        self.push_screen(QuitScreen(), check_quit)

    def action_open_settings(self) -> None:
        self.push_screen(SettingsScreen())

    async def action_return_home(self) -> None:
        channels = await load_channels()
        server = await self.channel_ops.get_server_info()

        if server is None:
            self.switch_mode("settings")
            return

        await self.push_screen("irc")
        for channel in channels:
            await self._ensure_channel_tab(channel)

        try:
            self.irc_client = self._make_irc_client(server, channels)
            self.irc_client.start_event_loop()
        except Exception as error:
            print(error)

    @on(ChatInput.Submitted)
    async def send_message(self, event) -> None:
        try:
            chat_input = self.get_screen("irc", IRCScreen).query_one(ChatInput)
        except NoMatches:
            chat_input = None

        if chat_input is None:
            return

        chat_input.value = ""

        try:
            self.tab = (
                self.get_screen("irc", IRCScreen).query_one(TabbedContent).active_pane
            )
            now = datetime.now()

            if now.minute <= 9 and event.value.split()[0] not in self.action_list:
                self.irc_client.connection.privmsg(
                    self.tab.name.replace("@", "").replace("+", ""),
                    event.value,
                )
                self.tab.mount(
                    Label(
                        f"{now.hour}:0{now.minute} "
                        f"<{self.irc_client.nickname}> {event.value}"
                    )
                )
            elif now.minute > 9 and event.value.split()[0] not in self.action_list:
                self.irc_client.connection.privmsg(
                    self.tab.name.replace("@", "").replace("+", ""),
                    event.value,
                )
                self.tab.mount(
                    Label(
                        f"{now.hour}:{now.minute} "
                        f"<{self.irc_client.nickname}> {event.value}"
                    )
                )
            elif event.value.split()[0] == "/join":
                await self.irc_client._intercept_join(event.value)
            elif event.value.split()[0] == "/part":
                await self.irc_client._intercept_part(event.value)
            elif event.value.split()[0] == "/whois":
                await self.irc_client._intercept_whois(event.value)

        except NoMatches:
            pass

    def get_channel_list(self):
        if self.channel_list is None:
            return None

        return self.channel_list

    def whois(self, nick):
        self.irc_client.connection.whois(nick)

    def irc_message(self, time, channel, sender, message, classes):
        self.tab = (
            self.get_screen("irc", IRCScreen)
            .query_one(TabbedContent)
            .get_pane(channel.replace("#", "").lower())
        )

        if self.irc_client.nickname in message:
            self.notify(f"{time} <{sender}> {message}", title=channel)
            self.tab.mount(
                Label(
                    f"{time} <{sender}> {message}",
                    classes="highlight",
                )
            )
        else:
            self.tab.mount(
                Label(
                    f"{time} <{sender}> {message}",
                    classes=classes,
                )
            )

    def received_private_message(self, time, sender, message, classes):
        tabbed_content = self.get_screen("irc", IRCScreen).query_one(TabbedContent)

        try:
            self.tab = tabbed_content.get_pane(sender)
            self.tab.mount(
                Label(
                    f"{time} <{sender}> {message}",
                    classes=classes,
                )
            )

            active_pane = tabbed_content.active_pane
            if active_pane != self.tab:
                self.notify(f"<{sender}> {message}", title="Private Message")

        except Exception:
            tabbed_content.add_pane(
                TabPane(
                    sender,
                    Label(),
                    name=sender,
                    id=sender,
                )
            )

            self.tab = tabbed_content.get_pane(sender)
            self.tab.mount(
                Label(
                    f"{time} <{sender}> {message}",
                    classes=classes,
                )
            )
            self.notify(f"<{sender}> {message}", title="Private Message")

    def add_to_tree(self, channel, user_list):
        tree = self.get_screen("irc", IRCScreen).query_one(ChannelTree)
        self.channel_list = self.get_channel_list()
        self.channel_ops = ChannelOperations()

        if self.channel_list is not None and channel != self.channel_list.data["id"]:
            channels_list = tree.root.add(channel, data={"id": channel})
            self.channel_list = channels_list
            self.node_list[channel] = channels_list
        elif self.channel_list is None:
            channels_list = tree.root.add(channel, data={"id": channel})
            self.channel_list = channels_list
            self.node_list[channel] = channels_list
        else:
            try:
                self.remove_from_tree(channel)
            except Exception:
                pass

            channels_list = tree.root.add(channel, data={"id": channel})
            self.channel_list = channels_list
            self.node_list[channel] = channels_list

        for user in user_list:
            self.channel_list.add_leaf(user, data={"id": user})

        for user in user_list:
            self.users.add(user)

    def remove_from_tree(self, channel):
        node = self.node_list[channel]
        node.remove()

    @work(group="irc-messages", exclusive=False, exit_on_error=False)
    async def handle_irc_message(self, time, channel, sender, message, classes):
        worker = get_current_worker()

        if not worker.is_cancelled:
            await self._ensure_channel_tab(channel)
            self.irc_message(time, channel, sender, message, classes)

    @work(
        group="irc-private-messages",
        exclusive=False,
        exit_on_error=False,
    )
    async def handle_private_message(self, time, sender, message, classes):
        worker = get_current_worker()

        if not worker.is_cancelled:
            self.received_private_message(time, sender, message, classes)

    async def on_shutdown(self):
        try:
            self.irc_client.on_disconnect()
        except AttributeError:
            pass


def main():
    app = TextChat()
    app.run()


if __name__ == "__main__":
    main()
