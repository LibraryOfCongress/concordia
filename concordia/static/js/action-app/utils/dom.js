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

export function sortChildren(container, sortKeyGenerator) {
    /*
        Sort all child nodes in a given container using the provided
        sortKeyExtractor function to obtain the sort key. The values should be
        anything which will work with a simple < or > comparison; if you want a
        reverse sort, multiply by -1 first.
    */

    // Since we will eventually be mutating the node list we will create an
    // Array with the full results now:
    let nodes = [...container.childNodes];

    // Build an Array of [nodes array index, sort key] pairs so we can extract
    // the values once and sort them in place:
    let sortKeys = Array.from(
        nodes.map((node, index) => [index, sortKeyGenerator(node)])
    );

    sortKeys
        .sort(([, a], [, b]) => {
            if (a < b) {
                return -1;
            } else if (a > b) {
                return 1;
            } else {
                return 0;
            }
        })
        .forEach(([index]) => {
            let child = nodes[index];
            container.appendChild(child);
        });
}
