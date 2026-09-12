from textchat.screens.context_menu import ContextMenu
from textchat.screens.context_menu import ContextTarget
from textchat.screens.private_message import PrivateMessageScreen
from textual import events
from textual.widgets import Tree


class ChannelTree(Tree):
    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Offer a private message when the selected node is a member."""
        data = event.node.data or {}
        if data.get("kind") != "user":
            return

        self.app.push_screen(PrivateMessageScreen(data["id"]))

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Open actions for the user or channel under a right-click."""
        if event.button != 3:
            return

        node_id = event.style.meta.get("node")
        if node_id is None:
            return

        node = self.get_node_by_id(node_id)
        data = node.data or {}
        kind = data.get("kind")
        value = data.get("id")
        if kind not in {"user", "channel"} or not value:
            return

        event.stop()
        target = ContextTarget(kind=kind, value=value)
        self.app.push_screen(
            ContextMenu(target),
            lambda action: self.app.handle_context_action(target, action),
        )

    def on_click(self, event: events.Click) -> None:
        """Keep a right-click from also selecting the Tree node."""
        if event.button == 3:
            event.prevent_default()
            event.stop()
