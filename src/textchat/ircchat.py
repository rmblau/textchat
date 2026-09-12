import hashlib
import re
from datetime import datetime
from pathlib import Path

from rich.style import Style
from rich.text import Text
from textchat.client import IRCApp
from textchat.client import WhoisInfo
from textchat.db.base import create_table
from textchat.db.db import ChannelOperations
from textchat.screens.irc import IRCScreen
from textchat.screens.quit import QuitScreen
from textchat.screens.settings import SettingsScreen
from textchat.screens.whois import WhoisScreen
from textchat.utils.channels import load_channels
from textchat.utils.nickcomplete import NickCompletion
from textchat.widgets.channeltree import ChannelTree
from textchat.widgets.chatmessage import ChatMessage
from textchat.widgets.input import ChatInput
from textual import on
from textual import work
from textual.app import App
from textual.css.query import NoMatches
from textual.widgets import Label
from textual.widgets import TabbedContent
from textual.widgets import TabPane
from textual.widgets._content_switcher import ContentSwitcher
from textual.widgets._tabbed_content import ContentTabs
from textual.worker import get_current_worker


class TextChat(App):
    # Resolve beside this module so running from the repository and from an
    # installed package use the same responsive stylesheet.
    CSS_PATH = Path(__file__).with_name("irc.tcss")
    URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")
    MESSAGE_PREFIX_PATTERN = re.compile(
        r"^(?P<time>\d{1,2}:\d{2}) <(?P<nickname>[^>]+)> "
    )
    NICK_COLORS = (
        "#d14f4f",
        "#f54d36",
        "#f5815d",
        "#d1692e",
        "#f5a65d",
        "#f5a836",
        "#d1ad4f",
        "#f5d636",
        "#f5ef5d",
        "#c4d12e",
        "#d6f55d",
        "#b8f536",
        "#98d14f",
        "#8af536",
        "#8ef55d",
        "#4fd12e",
        "#69f55d",
        "#36f53d",
        "#4fd164",
        "#36f56b",
        "#5df59a",
        "#2ed183",
        "#5df5be",
        "#36f5c7",
        "#4fd1c2",
        "#36f5f5",
        "#5de3f5",
        "#2eaad1",
        "#5dbef5",
        "#3699f5",
        "#4f83d1",
        "#366bf5",
        "#5d75f5",
        "#2e35d1",
        "#695df5",
        "#5c36f5",
        "#794fd1",
        "#8a36f5",
        "#b25df5",
        "#9d2ed1",
        "#d65df5",
        "#e636f5",
        "#d14fcc",
        "#f536d6",
        "#f55dca",
        "#d12e90",
        "#f55da6",
        "#f5367b",
        "#d14f6f",
        "#f5364d",
    )

    SCREENS = {
        "irc": IRCScreen,
        "settings": SettingsScreen,
    }

    BINDINGS = [
        ("ctrl+h", "return_home", "Home"),
        ("ctrl+s", "open_settings", "Settings"),
        ("ctrl+w", "close_current_tab", "Close tab"),
        ("ctrl+q", "request_quit", "Quit"),
        ("ctrl+d", "toggle_dark", "Toggle dark mode"),
        ("ctrl+shift+left", "move_tab_left", "Move tab left"),
        ("ctrl+shift+right", "move_tab_right", "Move tab right"),
    ]

    MODES = {
        "irc": IRCScreen,
        "settings": SettingsScreen,
        "quit": QuitScreen,
    }

    async def on_mount(self) -> None:
        await create_table()

        self.channel_list = None
        # IRC prefixes are per-channel: the same nick may be in one channel but
        # not another. Keep the list that powers the sidebar and completion in
        # the same channel-scoped structure.
        self.channel_users = {}
        self.node_list = {}
        self.unread_tabs = set()
        self.action_list = ["/join", "/part", "/msg", "/whois", "/close"]
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

    async def action_move_tab_left(self) -> None:
        await self._move_active_tab(-1)

    async def action_move_tab_right(self) -> None:
        await self._move_active_tab(1)

    async def _move_active_tab(self, direction: int) -> None:
        tabbed = self.get_screen("irc", IRCScreen).query_one(TabbedContent)
        active_pane = tabbed.active_pane
        if active_pane is None or active_pane.id is None:
            return

        switcher = tabbed.get_child_by_type(ContentSwitcher)
        panes = [pane for pane in switcher.children if isinstance(pane, TabPane)]
        index = panes.index(active_pane)
        destination = index + direction

        if not 0 <= destination < len(panes):
            return

        neighbor = panes[destination]
        tabs = tabbed.get_child_by_type(ContentTabs)
        tab_list = tabs.query_one("#tabs-list")

        active_tab = tabbed.get_tab(active_pane)
        neighbor_tab = tabbed.get_tab(neighbor)

        if direction < 0:
            tab_list.move_child(active_tab, before=neighbor_tab)
            switcher.move_child(active_pane, before=neighbor)
        else:
            tab_list.move_child(active_tab, after=neighbor_tab)
            switcher.move_child(active_pane, after=neighbor)

        tabbed.active = active_pane.id

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

    @staticmethod
    def _channel_key(channel):
        """Return the case-insensitive key used for IRC channel state."""
        return channel.casefold()

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
        active_pane = self.get_screen("irc").query_one(TabbedContent).active_pane
        if active_pane is None:
            return False

        channel = active_pane.name.casefold()
        state = getattr(chat_input, "nick_completion", None)

        if (
            state
            and state.channel == channel
            and chat_input.value == state.rendered_value
            and chat_input.cursor_position == state.cursor_position
        ):
            state.index = (state.index + 1) % len(state.candidates)
            nickname = state.candidates[state.index]
            replacement = nickname + state.suffix

            chat_input.value = state.before + replacement + state.after
            chat_input.cursor_position = len(state.before) + len(replacement)
            state.rendered_value = chat_input.value
            state.cursor_position = chat_input.cursor_position
            return True

        before_cursor = chat_input.value[: chat_input.cursor_position]
        match = re.search(r"(\S+)$", before_cursor)
        if match is None:
            return False

        prefix = match.group(1).lstrip("@+%&~")
        users = self.channel_users.get(channel, set())

        candidates = sorted(
            {
                user.lstrip("@+%&~")
                for user in users
                if user.lstrip("@+%&~").casefold().startswith(prefix.casefold())
            },
            key=str.casefold,
        )
        if not candidates:
            return False

        before = before_cursor[: match.start()]
        after = chat_input.value[chat_input.cursor_position :]
        suffix = ": " if match.start() == 0 else ""
        replacement = candidates[0] + suffix

        chat_input.value = before + replacement + after
        chat_input.cursor_position = len(before) + len(replacement)
        chat_input.nick_completion = NickCompletion(
            channel=channel,
            before=before,
            after=after,
            candidates=candidates,
            index=0,
            suffix=suffix,
            rendered_value=chat_input.value,
            cursor_position=chat_input.cursor_position,
        )
        return True

    @classmethod
    def _message_text(cls, message):
        text = Text(message)

        # Use a stable, readable color for each nick. ``hash()`` is avoided
        # because Python randomizes it between application launches.
        prefix = cls.MESSAGE_PREFIX_PATTERN.match(message)
        if prefix is not None:
            nickname = prefix.group("nickname")
            digest = hashlib.blake2b(
                nickname.casefold().encode("utf-8"),
                digest_size=4,
            ).digest()
            color_index = int.from_bytes(digest, "big") % len(cls.NICK_COLORS)
            text.stylize("dim", prefix.start(), prefix.start("nickname"))
            text.stylize(
                f"bold {cls.NICK_COLORS[color_index]}",
                prefix.start("nickname"),
                prefix.end("nickname"),
            )
            text.stylize(
                Style.from_meta({"pm": nickname}),
                prefix.start("nickname"),
                prefix.end("nickname"),
            )
            text.stylize("dim", prefix.end("nickname"), prefix.end())

        for match in cls.URL_PATTERN.finditer(message):
            url = match.group().rstrip(".,!?;:)]}")
            if not url:
                continue

            start = match.start()
            end = start + len(url)
            text.stylize("underline cyan", start, end)
            text.stylize(f"link {url}", start, end)

        return text

    @classmethod
    def _message_label(cls, message, classes=None):
        return ChatMessage(cls._message_text(message), markup=False, classes=classes)

    def _append_message(self, pane, message_label):
        """Mount a message and follow it once Textual has refreshed the layout."""
        pane.mount(message_label)
        tabbed_content = self.get_screen("irc", IRCScreen).query_one(TabbedContent)
        self.call_after_refresh(
            tabbed_content.scroll_end,
            animate=False,
            force=True,
        )

    def _set_tab_unread(self, pane, unread: bool) -> None:
        """Apply or remove the unread marker without changing the pane name."""
        if pane.id is None or pane.name is None:
            return

        tabbed_content = self.get_screen("irc", IRCScreen).query_one(TabbedContent)
        try:
            tab = tabbed_content.get_tab(pane)
        except NoMatches:
            return

        if unread:
            self.unread_tabs.add(pane.id)
        else:
            self.unread_tabs.discard(pane.id)

        label = f"* {pane.name}" if unread else pane.name
        if tab.label_text != label:
            tab.label = label

    def _mark_tab_unread_if_inactive(self, pane) -> None:
        tabbed_content = self.get_screen("irc", IRCScreen).query_one(TabbedContent)
        if tabbed_content.active_pane is not pane:
            self._set_tab_unread(pane, True)

    @on(TabbedContent.TabActivated)
    def clear_active_tab_unread(self, event: TabbedContent.TabActivated) -> None:
        """Read a tab as soon as the user switches to it."""
        self._set_tab_unread(event.pane, False)

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

    async def action_close_current_tab(self) -> None:
        """Hide the active tab without parting the ZNC channel."""
        tabbed_content = self.get_screen("irc", IRCScreen).query_one(TabbedContent)
        active_pane = tabbed_content.active_pane
        if active_pane is None or not active_pane.name:
            return

        await self._close_channel_tab(active_pane.name)

    async def _close_channel_tab(self, channel) -> None:
        """Remove one tab without sending an IRC PART command."""
        tabbed_content = self.get_screen("irc", IRCScreen).query_one(TabbedContent)
        pane_id = self._channel_pane_id(channel)
        try:
            tabbed_content.get_pane(pane_id)
        except NoMatches:
            return
        await tabbed_content.remove_pane(pane_id)

    @work(group="private-messages", exclusive=False, exit_on_error=False)
    async def open_private_message(self, nickname) -> None:
        """Open and select a private-message tab for an IRC nickname."""
        nickname = nickname.lstrip("@+%&~")
        if not nickname:
            return

        tabbed_content = self.get_screen("irc", IRCScreen).query_one(TabbedContent)
        try:
            tabbed_content.get_pane(nickname)
        except NoMatches:
            await tabbed_content.add_pane(
                TabPane(nickname, Label(), name=nickname, id=nickname)
            )
        tabbed_content.active = nickname

    @work(group="channel-tabs", exclusive=False, exit_on_error=False)
    async def open_channel_tab(self, channel) -> None:
        await self._ensure_channel_tab(channel)
        tabbed_content = self.get_screen("irc", IRCScreen).query_one(TabbedContent)
        tabbed_content.active = self._channel_pane_id(channel)

    @work(group="channel-tabs", exclusive=False, exit_on_error=False)
    async def close_channel_tab(self, channel) -> None:
        await self._close_channel_tab(channel)

    @work(group="channel-parts", exclusive=False, exit_on_error=False)
    async def part_channel(self, channel) -> None:
        await self.irc_client.part_channel(channel)

    async def part_current_channel(self) -> None:
        """Part the active IRC channel, but never treat a PM as a channel."""
        tabbed_content = self.get_screen("irc", IRCScreen).query_one(TabbedContent)
        active_pane = tabbed_content.active_pane
        channel = active_pane.name if active_pane is not None else None

        if not channel or channel[0] not in "#&!+":
            self.notify("/part must be used from a channel tab")
            return

        await self.irc_client.part_channel(channel)

    def request_whois(self, nickname) -> None:
        self.irc_client.request_whois(nickname)

    @work(group="whois-results", exclusive=False, exit_on_error=False)
    async def handle_whois_result(self, info: WhoisInfo) -> None:
        await self.push_screen(WhoisScreen(info))

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

    async def _handle_chat_command(self, message) -> None:
        """Dispatch commands handled by Textchat itself."""
        command, _, argument = message.partition(" ")

        if command == "/join":
            await self.irc_client._intercept_join(message)
        elif command == "/part":
            if argument.strip():
                await self.irc_client._intercept_part(message)
            else:
                await self.part_current_channel()
        elif command == "/whois":
            await self.irc_client._intercept_whois(message)
        elif command == "/close":
            await self.action_close_current_tab()

    async def _send_plain_message(self, message) -> None:
        """Send and render a non-command message in the active tab."""
        try:
            self.tab = (
                self.get_screen("irc", IRCScreen).query_one(TabbedContent).active_pane
            )
        except NoMatches:
            return

        if self.tab is None or not self.tab.name:
            return

        self.irc_client.connection.privmsg(
            self.tab.name.replace("@", "").replace("+", ""),
            message,
        )
        now = datetime.now().strftime("%H:%M")
        self._append_message(
            self.tab,
            self._message_label(f"{now} <{self.irc_client.nickname}> {message}"),
        )

    @on(ChatInput.Submitted)
    async def send_message(self, event) -> None:
        try:
            chat_input = self.get_screen("irc", IRCScreen).query_one(ChatInput)
        except NoMatches:
            return

        chat_input.value = ""
        message = event.value.strip()
        if not message:
            return

        command = message.split(maxsplit=1)[0]
        if command in self.action_list:
            await self._handle_chat_command(message)
        else:
            await self._send_plain_message(message)

    def get_channel_list(self):
        if self.channel_list is None:
            return None

        return self.channel_list

    def irc_message(
        self,
        time,
        channel,
        sender,
        message,
        classes,
        mark_unread=True,
    ):
        self.tab = (
            self.get_screen("irc", IRCScreen)
            .query_one(TabbedContent)
            .get_pane(channel.replace("#", "").lower())
        )

        if self.irc_client.nickname in message:
            self.notify(f"{time} <{sender}> {message}", title=channel)
            self._append_message(
                self.tab,
                self._message_label(
                    f"{time} <{sender}> {message}",
                    classes="highlight",
                ),
            )
        else:
            self._append_message(
                self.tab,
                self._message_label(
                    f"{time} <{sender}> {message}",
                    classes=classes,
                ),
            )

        if mark_unread:
            self._mark_tab_unread_if_inactive(self.tab)

    def received_private_message(self, time, sender, message, classes):
        tabbed_content = self.get_screen("irc", IRCScreen).query_one(TabbedContent)

        try:
            self.tab = tabbed_content.get_pane(sender)
            self._append_message(
                self.tab,
                self._message_label(
                    f"{time} <{sender}> {message}",
                    classes=classes,
                ),
            )

            active_pane = tabbed_content.active_pane
            if active_pane != self.tab:
                self.notify(f"<{sender}> {message}", title="Private Message")

            self._mark_tab_unread_if_inactive(self.tab)

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
            self._append_message(
                self.tab,
                self._message_label(
                    f"{time} <{sender}> {message}",
                    classes=classes,
                ),
            )
            self._mark_tab_unread_if_inactive(self.tab)
            self.notify(f"<{sender}> {message}", title="Private Message")

    def add_to_tree(self, channel, user_list):
        """Render one channel's current member list in the sidebar."""
        tree = self.get_screen("irc", IRCScreen).query_one(ChannelTree)
        channel_key = self._channel_key(channel)
        self.channel_users[channel_key] = set(user_list)

        existing_node = self.node_list.pop(channel_key, None)
        if existing_node is not None:
            existing_node.remove()

        channel_node = tree.root.add(
            channel,
            data={"id": channel, "kind": "channel"},
        )
        self.node_list[channel_key] = channel_node
        self.channel_list = channel_node

        for user in sorted(
            user_list,
            key=lambda nickname: nickname.lstrip("@+%&~").casefold(),
        ):
            channel_node.add_leaf(user, data={"id": user, "kind": "user"})

    def remove_from_tree(self, channel):
        channel_key = self._channel_key(channel)
        node = self.node_list.pop(channel_key, None)
        if node is not None:
            node.remove()
        self.channel_users.pop(channel_key, None)

    @work(group="irc-messages", exclusive=False, exit_on_error=False)
    async def handle_irc_message(
        self,
        time,
        channel,
        sender,
        message,
        classes,
        mark_unread=True,
    ):
        worker = get_current_worker()

        if not worker.is_cancelled:
            await self._ensure_channel_tab(channel)
            self.irc_message(
                time,
                channel,
                sender,
                message,
                classes,
                mark_unread,
            )

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
            self.irc_client.stop()
        except AttributeError:
            pass


def main():
    app = TextChat()
    app.run()


if __name__ == "__main__":
    main()
