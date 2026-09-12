from textual.widgets import Tree


class ChannelTree(Tree):
    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Show WHOIS details when a member is selected in the channel tree."""
        data = event.node.data or {}
        if data.get("kind") != "user":
            return

        self.app.request_whois(data["id"])
