from textual.widgets import Tree
from textchat.screens.whois import WhoisScreen

class ChannelTree(Tree):
   def on_tree_node_selected(self, node: Tree) -> None:
        whois = WhoisScreen()
        self.app.whois(node.node.data['id'])
        self.app.user = node.node.data['id']
        self.app.push_screen(whois)