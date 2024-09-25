/* global turnstile */

function resetTurnstile(widgetId) {
    // widgetId is optional. If not provided, the latest
    // turnstile widget is used automatically
    if (turnstile && typeof turnstile.reset === 'function') {
        turnstile.reset(widgetId);
    } else {
        console.error(
            'Unable to reset turnstile. Turnstile.reset is not a function.',
        );
    }
}

export {resetTurnstile};
