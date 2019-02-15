export function emptyNode(node) {
    while (node.lastChild) {
        node.lastChild.remove();
    }
}
