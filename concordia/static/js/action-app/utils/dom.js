export function $(selector, scope = document) {
    return scope.querySelector(selector);
}

export function $$(selector, scope = document) {
    return Array.from(scope.querySelectorAll(selector));
}

export function emptyNode(node) {
    while (node.lastChild) {
        node.lastChild.remove();
    }
}
