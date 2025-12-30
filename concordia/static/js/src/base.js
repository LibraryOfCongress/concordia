import 'bootstrap';
import Cookies from 'js-cookie';
import $ from 'jquery';
import screenfull from 'screenfull';
import {Popover} from 'bootstrap';
import * as Sentry from '@sentry/browser';

(function () {
    /*
        Configure jQuery to use CSRF tokens automatically — see
        https://docs.djangoproject.com/en/2.1/ref/csrf/#setting-the-token-on-the-ajax-request
    */

    var CSRFCookie = Cookies.get('csrftoken');

    if (!CSRFCookie) {
        return;
    }

    function csrfSafeMethod(method) {
        // these HTTP methods do not require CSRF protection
        return /^(GET|HEAD|OPTIONS|TRACE)$/.test(method);
    }

    $.ajaxSetup({
        beforeSend: function (xhr, settings) {
            if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
                xhr.setRequestHeader('X-CSRFToken', CSRFCookie);
            }
        },
    });
})();

document.addEventListener('DOMContentLoaded', () => {
    const popoverTriggerList = document.querySelectorAll(
        '[data-bs-toggle="popover"]',
    );
    for (const popoverTriggerElement of popoverTriggerList) {
        new Popover(popoverTriggerElement);
    }
});

// eslint-disable-next-line no-unused-vars
export function buildErrorMessage(jqXHR, textStatus, errorThrown) {
    /* Construct a nice error message using optional JSON response context */
    var errorMessage;
    // eslint-disable-next-line unicorn/prefer-ternary
    if (jqXHR.responseJSON && jqXHR.responseJSON.error) {
        errorMessage = jqXHR.responseJSON.error;
    } else {
        errorMessage = textStatus + ' ' + errorThrown;
    }
    return errorMessage;
}

export function displayHtmlMessage(level, message, uniqueId) {
    /*
        Display a dismissable message at a level which will match one of the
        Bootstrap alert classes
        (https://getbootstrap.com/docs/5.3/components/alerts/)

        If provided, uniqueId will be used to remove any existing elements which
        have that ID, allowing old messages to be replaced automatically.
    */
    let $messages = $('#messages');
    $messages.removeAttr('hidden');

    let $newMessage = $messages
        .find('#message-template .alert')
        .clone()
        .removeAttr('hidden')
        .removeAttr('id');

    if (level == 'error') {
        // Class for red background
        level = 'danger';
    }

    $newMessage.addClass('alert-' + level);

    if (uniqueId) {
        $('#' + uniqueId).remove();
        $newMessage.attr('id', uniqueId);
    }

    // Add a span to the message to ensure justified
    // styles don't end up splitting the text
    // message might be a Text node, so we need to get
    // the actual text if so
    if (message instanceof Text) {
        message = message.textContent;
    }
    $newMessage.prepend('<span>' + message + '</span>');

    $messages.append($newMessage);

    return $newMessage;
}

export function displayMessage(level, message, uniqueId) {
    return displayHtmlMessage(
        level,
        document.createTextNode(message),
        uniqueId,
    );
}

function isOutdatedBrowser() {
    /*
        See https://caniuse.com/#feat=css-supports-api for the full matrix but
        by now this is effectively the same as testing for IE11 vs. all of the
        evergreen browsers:
    */
    return typeof CSS == 'undefined' || !CSS.supports;
}

function loadLegacyPolyfill(scriptUrl, callback) {
    var script = document.createElement('script');
    script.type = 'text/javascript';
    script.async = false;
    // eslint-disable-next-line unicorn/prefer-add-event-listener
    script.onload = callback;
    // eslint-disable-next-line unicorn/prevent-abbreviations
    script.src = scriptUrl;
    document.body.append(script);
}

document.addEventListener('DOMContent', () => {
    if (isOutdatedBrowser()) {
        var theMessage =
            'You are using an outdated browser. This website fully supports the current ' +
            'version of every major browser ' +
            '(Microsoft Edge, Google Chrome, Mozilla Firefox, and Apple Safari). See ' +
            'our <a href="/help-center/#browserSupport">browser support policy</a> ' +
            'for more information.';

        var warningCookie = 'outdated-browser-message-hidden';
        var warningLastShown = 0;
        try {
            var cookie = Cookies.get(warningCookie);
            if (cookie) {
                warningLastShown = Number.parseInt(cookie, 10);
            }
        } catch (error) {
            Sentry.captureException(error);
        }

        if (Date.now() - warningLastShown > 7 * 86_400) {
            displayHtmlMessage('danger', theMessage).on(
                'closed.bs.alert',
                function () {
                    Cookies.set(warningCookie, Date.now());
                },
            );
        }

        /*
            CSS variables are supported by everything except IE11:
            https://caniuse.com/#feat=css-variables
        */
        loadLegacyPolyfill(
            'https://cdn.jsdelivr.net/npm/css-vars-ponyfill@2.0.2/dist/css-vars-ponyfill.min.js',
            function () {
                /* global cssVars */
                cssVars({
                    legacyOnly: true,
                    preserveStatic: true,
                    include: 'link[rel="stylesheet"][href^="/static/"]',
                });
            },
        );
    }
});

if (screenfull.isEnabled) {
    $('#go-fullscreen')
        .removeAttr('hidden')
        .on('click', function (event) {
            event.preventDefault();
            var targetElement = document.getElementById(this.dataset.bsTarget);

            if (screenfull.isFullscreen) {
                screenfull.exit();
            } else {
                screenfull.request(targetElement);
            }
        });
}

function appendAccountItem(link, $menu) {
    if (link.type !== 'post') {
        $('<a>')
            .addClass('dropdown-item')
            .attr('href', link.url)
            .text(link.title)
            .appendTo($menu);
        return;
    }

    const csrfToken = Cookies.get('csrftoken');
    const formId =
        'nav-post-' + link.title.toLowerCase().replaceAll(/[^\da-z]+/g, '-');

    const $form = $('<form>')
        .attr({id: formId, method: 'post', action: link.url})
        .css('display', 'none')
        .appendTo(document.body);

    // Django expects the hidden field name "csrfmiddlewaretoken"
    $('<input>')
        .attr({type: 'hidden', name: 'csrfmiddlewaretoken', value: csrfToken})
        .appendTo($form);

    if (link.fields) {
        for (const [name, value] of Object.entries(link.fields)) {
            $('<input>')
                .attr({type: 'hidden', name: name, value: value})
                .appendTo($form);
        }
    }

    $('<button>')
        .addClass('dropdown-item')
        .attr({type: 'submit', form: formId})
        .text(link.title)
        .appendTo($menu);
}

$.ajax({
    url: '/account/ajax-status/',
    method: 'GET',
    dataType: 'json',
    cache: true,
}).done(function (data) {
    if (!data.username) {
        return;
    }

    $('.anonymous-only').remove();
    $('.authenticated-only').removeAttr('hidden');
    if (data.links) {
        var $accountDropdown = $('#topnav-account-dropdown');
        $('<a>')
            .addClass('nav-link fw-bold')
            .attr({
                id: 'topnav-account-dropdown-toggle',
                'data-bs-toggle': 'dropdown',
                'aria-haspopup': 'true',
                'aria-expanded': 'false',
            })
            .text(data.username + ' ')
            .prependTo($accountDropdown);
        $('<span>')
            .addClass('fa fa-chevron-down text-primary')
            .appendTo('#topnav-account-dropdown-toggle');
        var $accountDropdownMenu = $('<div>');
        $accountDropdownMenu
            .addClass('dropdown-menu')
            .attr('aria-labelledby', 'topnav-account-dropdown-toggle')
            .appendTo($accountDropdown);
        for (const link of data.links) {
            appendAccountItem(link, $accountDropdownMenu);
        }
    }
});

$.ajax({url: '/account/ajax-messages/', method: 'GET', dataType: 'json'}).done(
    function (data) {
        if (data.messages) {
            for (const message of data.messages) {
                displayMessage(message.level, message.message);
            }
        }
    },
);

// eslint-disable-next-line no-unused-vars
export function debounce(function_, timeout = 300) {
    // Based on https://www.freecodecamp.org/news/javascript-debounce-example/
    let timer;
    return (...arguments_) => {
        clearTimeout(timer);
        timer = setTimeout(() => {
            function_.apply(this, arguments_);
        }, timeout);
    };
}

/* Social share stuff */

var hideTooltip = function (tooltipButton) {
    return function () {
        tooltipButton.tooltip('hide');
    };
};

var hideTooltipCallback = function () {
    // wait a couple seconds and then hide the tooltip.
    setTimeout(hideTooltip($(this)), 3000);
};

function trackShareInteraction($element, interactionType) {
    // Adobe analytics user interaction tracking
    if ('loc_ux_tracking' in window) {
        let loc_ux_tracking = window['loc_ux_tracking'];
        loc_ux_tracking.trackUserInteractionEvent(
            $element,
            'Share Tool',
            'click',
            interactionType,
        );
    }
}

var $copyUrlButton = $('.copy-url-button');
var $facebookShareButton = $('.facebook-share-button');
var $twitterShareButton = $('.twitter-share-button');

const copyUrlButton = document.querySelector('.copy-url-button');
if (copyUrlButton) {
    copyUrlButton.addEventListener('click', function (event) {
        event.preventDefault();

        // The asynchronous Clipboard API is not supported by Microsoft Edge or Internet Explorer:
        // https://developer.mozilla.org/en-US/docs/Web/API/Clipboard/writeText#Browser_compatibility
        // We'll use the older document.execCommand("copy") interface which requires a text input:
        var $clipboardInput = $('<input type="text">')
            .val($copyUrlButton.attr('href'))
            .insertAfter($copyUrlButton);
        $clipboardInput.get(0).select();

        var tooltipMessage = '';

        trackShareInteraction($copyUrlButton, 'Link copy');

        try {
            document.execCommand('copy');
            // Show the tooltip with a success message
            tooltipMessage = 'This link has been copied to your clipboard';
            $copyUrlButton
                .tooltip('dispose')
                .tooltip({title: tooltipMessage})
                .tooltip('show')
                .on('shown.bs.tooltip', hideTooltipCallback);
        } catch (error) {
            if (Sentry !== 'undefined') {
                Sentry.captureException(error);
            }

            // Display an error message in the tooltip
            tooltipMessage =
                '<p>Could not access your clipboard.</p><button class="btn btn-light btn-sm" id="dismiss-tooltip-button">Close</button>';
            $copyUrlButton
                .tooltip('dispose')
                .tooltip({title: tooltipMessage, html: true})
                .tooltip('show');
            document
                .querySelector('#dismiss-tooltip-button')
                .addEventListener('click', function () {
                    $copyUrlButton.tooltip('hide');
                });
        } finally {
            $clipboardInput.remove();
        }

        return false;
    });
}

const fbShareButton = document.querySelector('.copy-url-button');
if (fbShareButton) {
    fbShareButton.addEventListener('click', function () {
        trackShareInteraction($facebookShareButton, 'Facebook Share');
        return true;
    });
}

const xShareButton = document.querySelector('.twitter-share-button');
if (xShareButton) {
    xShareButton.addEventListener('click', function () {
        trackShareInteraction($twitterShareButton, 'Twitter Share');
        return true;
    });
}

// eslint-disable-next-line no-unused-vars
export function trackUIInteraction(element, category, action, label) {
    if ('loc_ux_tracking' in window) {
        let loc_ux_tracking = window['loc_ux_tracking'];
        let data = [element, category, action, label];
        loc_ux_tracking.trackUserInteractionEvent(...data);
    }
}
