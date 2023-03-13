export function $(selector, scope = document) {
    return scope.querySelector(selector);
}

export function $$(selector, scope = document) {
    return [...scope.querySelectorAll(selector)];
}

export function setSelectValue(selectElement, value) {
    // Set the value of the provided HTMLSelectElement only if it's not null
    // and the <select> currently contains an <option> with that value:
    if (value != undefined) {
        $$('option', selectElement).forEach((option) => {
            if (option.value == value) {
                selectElement.value = option.value;
            }
        });
    }
}
