from textual.widgets import Tree


class ChannelTree(Tree):
    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Select the channel and show its members in the roster sidebar."""
        data = event.node.data or {}
        if data.get("kind") != "channel":
            return

        self.app.select_sidebar_channel(data["id"])
