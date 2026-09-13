import hashlib
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from irc.client import ServerNotConnectedError
from rich.style import Style
from rich.text import Text
from textchat.client import IRCApp
from textchat.client import WhoisInfo
from textchat.db.base import create_table
from textchat.db.db import ChannelOperations
from textchat.notifications import send_desktop_notification
from textchat.screens.irc import IRCScreen
from textchat.screens.kicked import KickedScreen
from textchat.screens.networks import NetworkPickerScreen
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
from textual.widgets import Static
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
    SLEEP_GAP_SECONDS = 15

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
        self.channel_topics = {}
        self.node_list = {}
        self.tab_drafts = {}
        self.unread_tabs = set()
        self.active_server_id = None
        self._last_awake_wall_time = time.time()
        self._wake_reconnect_pending = False
        self._wake_monitor_started = False
        self.action_list = [
            "/join",
            "/part",
            "/msg",
            "/whois",
            "/close",
            "/kick",
            "/nick",
        ]
        self.channel_ops = ChannelOperations()
        self.irc_screen = self.get_screen("irc", IRCScreen)

        servers = await self.channel_ops.get_servers()
        if not servers:
            self.switch_mode("settings")
            return

        await self.show_network_picker()

    @on(ChatInput.Changed)
    def save_active_tab_draft(self, event: ChatInput.Changed) -> None:
        """Keep the current input text with its active channel or PM tab."""
        try:
            tabbed = self.get_screen("irc", IRCScreen).query_one(TabbedContent)
        except NoMatches:
            # Textual can emit a final Changed event while the IRC screen is
            # being removed during shutdown, after its tab container is gone.
            return
        pane = tabbed.active_pane

        if pane is not None and pane.id is not None:
            self.tab_drafts[pane.id] = event.value

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
            server_list=[(server.connection_address, server.port)],
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

    def update_topic_bar(self, channel: str | None) -> None:
        """Render the active channel's cached IRC topic below the sidebar."""
        try:
            topic_bar = self.get_screen("irc", IRCScreen).query_one(
                "#topic-bar", Static
            )
        except NoMatches:
            return

        if not channel or channel[0] not in "#&!+":
            topic_bar.update("No channel selected")
            return

        topic = self.channel_topics.get(channel.casefold(), "")
        topic_bar.update(f"({channel}) {topic or 'No topic set'}")

    @work(group="channel-topics", exclusive=False, exit_on_error=False)
    async def update_channel_topic(self, channel: str, topic: str) -> None:
        """Cache a topic received from IRC and refresh it if it is visible."""
        self.channel_topics[channel.casefold()] = topic

        try:
            tabbed = self.get_screen("irc", IRCScreen).query_one(TabbedContent)
        except NoMatches:
            return
        active_pane = tabbed.active_pane
        if (
            active_pane is not None
            and active_pane.name is not None
            and active_pane.name.casefold() == channel.casefold()
        ):
            self.update_topic_bar(channel)

    @on(TabbedContent.TabActivated)
    def clear_active_tab_unread(self, event: TabbedContent.TabActivated) -> None:
        """Read a tab as soon as the user switches to it."""
        self._set_tab_unread(event.pane, False)
        self.update_topic_bar(event.pane.name)
        chat_input = self.get_screen("irc", IRCScreen).query_one(ChatInput)
        draft = self.tab_drafts.get(event.pane.id, "")
        chat_input.value = draft
        chat_input.cursor_position = len(draft)
        chat_input.nick_completion = None
        self.call_after_refresh(
            event.tabbed_content.scroll_end,
            animate=False,
            force=True,
        )

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

    async def show_network_picker(self) -> None:
        """Show saved profiles and connect only after the user selects one."""
        servers = await self.channel_ops.get_servers()
        if not servers:
            self.switch_mode("settings")
            return

        def connect_selected(selection: int | str) -> None:
            if selection == "settings":
                self.action_open_settings()
            elif isinstance(selection, int):
                self.call_after_refresh(self.connect_saved_server, selection)

        self.push_screen(NetworkPickerScreen(servers), connect_selected)

    async def action_close_current_tab(self) -> None:
        """Hide the active tab without parting the ZNC channel."""
        tabbed_content = self.get_screen("irc", IRCScreen).query_one(TabbedContent)
        active_pane = tabbed_content.active_pane
        if active_pane is None or not active_pane.name:
            return
        self.tab_drafts.pop(active_pane.id, None)
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
        """Return from settings without replacing an active IRC connection."""
        if hasattr(self, "irc_client"):
            if isinstance(self.screen, SettingsScreen):
                await self.pop_screen()
            return

        if self.current_mode == "settings":
            self.switch_mode("irc")
        await self.show_network_picker()

    async def kick_from_current_channel(self, argument: str) -> None:
        tabbed = self.get_screen("irc", IRCScreen).query_one(TabbedContent)
        pane = tabbed.active_pane
        channel = pane.name if pane else None

        if not channel or channel[0] not in "#&!+":
            self.notify("/kick must be used from a channel tab")
            return

        nickname, _, reason = argument.strip().partition(" ")
        if not nickname:
            self.notify("Usage: /kick <nickname> [reason]")
            return

        self.irc_client.connection.kick(
            channel,
            nickname.lstrip("@+%&~"),
            reason.strip(),
        )

    @work(group="kicked-channel", exclusive=False, exit_on_error=False)
    async def handle_local_kick(
        self,
        channel: str,
        kicker: str,
        reason: str,
    ) -> None:
        """Offer a local user a deliberate way to rejoin a kicked channel."""

        def handle_choice(rejoin: bool) -> None:
            if not rejoin:
                return

            self.notify(f"Rejoining ({channel})…", title="Textchat")
            self.irc_client.connection.join(channel)

        self.push_screen(KickedScreen(channel, kicker, reason), handle_choice)

    def _detect_wake(self) -> None:
        """Reconnect after the event loop resumes from computer sleep."""
        now = time.time()
        elapsed = now - self._last_awake_wall_time
        self._last_awake_wall_time = now

        if elapsed < self.SLEEP_GAP_SECONDS:
            return

        self._request_reconnect("Reconnecting after wake…")

    def _request_reconnect(self, message: str) -> bool:
        """Start one reconnect worker and make its reason visible to the user."""
        if (
            self._wake_reconnect_pending
            or self.active_server_id is None
            or not hasattr(self, "irc_client")
        ):
            return False

        self._wake_reconnect_pending = True
        self.notify(message, title="Textchat")
        self.reconnect_after_wake(self.active_server_id)
        return True

    def _start_wake_monitor(self) -> None:
        """Start one sleep-gap monitor for both first-run and later connects."""
        self._last_awake_wall_time = time.time()
        if not self._wake_monitor_started:
            self.set_interval(5, self._detect_wake)
            self._wake_monitor_started = True

    @work(group="wake-reconnect", exclusive=True, exit_on_error=False)
    async def reconnect_after_wake(self, server_id) -> None:
        try:
            await self.connect_saved_server(server_id)
        finally:
            self._wake_reconnect_pending = False

    async def _reset_connection_view(self) -> None:
        """Remove the previous server's tabs and member tree before reconnecting."""
        try:
            irc_screen = self.get_screen("irc", IRCScreen)
            tabbed_content = irc_screen.query_one(TabbedContent)
            tree = irc_screen.query_one(ChannelTree)
        except NoMatches:
            return

        switcher = tabbed_content.get_child_by_type(ContentSwitcher)
        panes = [pane for pane in switcher.children if isinstance(pane, TabPane)]
        for pane in panes:
            if pane.id is not None:
                await tabbed_content.remove_pane(pane.id)

        tree.clear()
        self.channel_users.clear()
        self.channel_topics.clear()
        self.node_list.clear()
        self.unread_tabs.clear()
        self.channel_list = None

    async def connect_saved_server(self, server_id) -> None:
        """Make one saved profile active and reconnect the single IRC client."""
        server = await self.channel_ops.get_server_info(server_id)
        if server is None:
            self.notify("That server profile no longer exists.")
            return

        await self.channel_ops.set_active_server(server.id)
        self.active_server_id = server.id

        try:
            self.irc_client.stop()
        except AttributeError:
            pass

        irc_screen = self.get_screen("irc", IRCScreen)
        if self.screen is not irc_screen:
            # Always return to the installed IRC screen. Switching modes here
            # would create a second, empty IRCScreen while channel tabs are
            # added to this installed instance.
            await self.push_screen("irc")

        await self._reset_connection_view()
        channels = await load_channels(server.id)
        for channel in channels:
            await self._ensure_channel_tab(channel)

        self.irc_client = self._make_irc_client(server, channels)
        self.irc_client.start_event_loop()
        self._start_wake_monitor()

    async def _handle_chat_command(self, message) -> None:
        """Dispatch commands handled by Textchat itself."""
        command, _, argument = message.partition(" ")
        match command:
            case "/join":
                await self.irc_client._intercept_join(message)

            case "/part":
                if argument.strip():
                    await self.irc_client._intercept_part(message)
                else:
                    await self.part_current_channel()

            case "/whois":
                await self.irc_client._intercept_whois(message)

            case "/close":
                await self.action_close_current_tab()

            case "/kick":
                if argument.lstrip().startswith(("#", "&", "!", "+")):
                    await self.irc_client._intercept_kick(message)
                else:
                    await self.kick_from_current_channel(argument)
            case "/nick":
                await self.irc_client._intercept_nick(message)

            case _:
                self.notify(f"Unknown command: {command}")

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

        try:
            self.irc_client.connection.privmsg(
                self.tab.name.replace("@", "").replace("+", ""),
                message,
            )
        except ServerNotConnectedError:
            self._request_reconnect(
                "Connection lost. Reconnecting… Message was not sent."
            )
            return
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

    def _notify(self, message: str, title: str) -> None:
        """Show Textual's notice and, on macOS, a native desktop notification."""
        self.notify(message, title=title)
        self.send_macos_notification(title, message)

    @work(
        group="macos-notifications",
        exclusive=False,
        exit_on_error=False,
    )
    async def send_macos_notification(self, title: str, message: str) -> None:
        await send_desktop_notification(title, message)

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
            self._notify(f"{time} <{sender}> {message}", title=channel)
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
                self._notify(f"<{sender}> {message}", title="Private Message")

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
            self._notify(f"<{sender}> {message}", title="Private Message")

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
        self.channel_topics.pop(channel_key, None)

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


def _macos_event_loop():
    """Create an asyncio loop which can receive macOS notification callbacks."""
    from ctypes import cdll
    from ctypes import util

    appkit = util.find_library("AppKit")
    if appkit is None:
        raise RuntimeError("Unable to load macOS AppKit framework")

    # Rubicon resolves NSEvent during import, so AppKit must be loaded first.
    cdll.LoadLibrary(appkit)

    from rubicon.objc.eventloop import RubiconEventLoop

    return RubiconEventLoop()


def main():
    app = TextChat()

    if sys.platform == "darwin":
        app.run(loop=_macos_event_loop())
    else:
        app.run()


if __name__ == "__main__":
    main()
