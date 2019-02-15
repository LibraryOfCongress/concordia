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

export function sortChildren(container, comparisonFunction) {
    [...container.childNodes]
        .sort(comparisonFunction)
        .forEach(child => container.appendChild(child));
}
