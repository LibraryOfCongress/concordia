/* global $ Cookies screenfull raven */
/* exported displayMessage buildErrorMessage */

(function() {
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
        beforeSend: function(xhr, settings) {
            if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
                xhr.setRequestHeader('X-CSRFToken', CSRFCookie);
            }
        }
    });
})();

$(function() {
    $('[data-toggle="popover"]').popover();
});

function buildErrorMessage(jqXHR, textStatus, errorThrown) {
    /* Construct a nice error message using optional JSON response context */
    var errMessage;
    if (jqXHR.responseJSON && jqXHR.responseJSON.error) {
        errMessage = jqXHR.responseJSON.error;
    } else {
        errMessage = textStatus + ' ' + errorThrown;
    }
    return errMessage;
}

function displayHtmlMessage(level, message, uniqueId) {
    /*
        Display a dismissable message at a level which will match one of the
        Bootstrap alert classes
        (https://getbootstrap.com/docs/4.1/components/alerts/)

        If provided, uniqueId will be used to remove any existing elements which
        have that ID, allowing old messages to be replaced automatically.
    */
    var $messages = $('#messages');
    $messages.removeAttr('hidden');

    var $newMessage = $messages
        .find('#message-template .alert')
        .clone()
        .removeAttr('hidden')
        .removeAttr('id');

    $newMessage.addClass('alert-' + level);

    if (uniqueId) {
        $('#' + uniqueId).remove();
        $newMessage.attr('id', uniqueId);
    }

    $newMessage.prepend(message);

    $messages.append($newMessage);

    return $newMessage;
}

function displayMessage(level, message, uniqueId) {
    return displayHtmlMessage(
        level,
        document.createTextNode(message),
        uniqueId
    );
}

function isOutdatedBrowser() {
    /* See https://caniuse.com/#feat=css-supports-api */
    return typeof CSS == 'undefined' || !CSS.supports;
}

function loadLegacyPolyfill(scriptUrl, callback) {
    var script = document.createElement('script');
    script.type = 'text/javascript';
    script.async = false;
    script.onload = callback;
    script.src = scriptUrl;
    document.body.appendChild(script);
}

$(function() {
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
                warningLastShown = parseInt(cookie, 10);
            }
        } catch (e) {
            raven.captureMessage(e);
        }

        if (Date.now() - warningLastShown > 7 * 86400) {
            displayHtmlMessage('danger', theMessage).on(
                'closed.bs.alert',
                function() {
                    Cookies.set(warningCookie, Date.now());
                }
            );
        }

        loadLegacyPolyfill(
            'https://cdn.jsdelivr.net/npm/css-vars-ponyfill@1.12.0/dist/css-vars-ponyfill.min.js',
            function() {
                /* global cssVars */
                cssVars({
                    legacyOnly: true,
                    onlyVars: true,
                    include: 'link[rel="stylesheet"][href^="/static/"]'
                });
            }
        );
    }

    if (location.hash && $('#faqAccordion').length > 0) {
        $(location.hash).on('shown.bs.collapse', function() {
            window.location = location.hash;
        });
        $(location.hash).collapse('show');
    }
});

if (screenfull.enabled) {
    $('#go-fullscreen')
        .removeAttr('hidden')
        .on('click', function(evt) {
            evt.preventDefault();
            var targetElement = document.getElementById(this.dataset.target);

            if (screenfull.isFullscreen) {
                screenfull.exit();
            } else {
                screenfull.request(targetElement);
            }
        });
}

$.ajax({
    url: '/account/ajax-status/',
    method: 'GET',
    dataType: 'json',
    cache: true
}).done(function(data) {
    if (!data.username) {
        return;
    }

    $('.anonymous-only').remove();
    $('.authenticated-only').removeAttr('hidden');
    if (data.links) {
        var $accountMenu = $('#topnav-account-dropdown .dropdown-menu');
        data.links.forEach(function(i) {
            $('<a>')
                .addClass('dropdown-item')
                .attr('href', i.url)
                .text(i.title)
                .prependTo($accountMenu);
        });
    }
});

$.ajax({url: '/account/ajax-messages/', method: 'GET', dataType: 'json'}).done(
    function(data) {
        if (data.messages) {
            data.messages.forEach(function(message) {
                displayMessage(message.level, message.message);
            });
        }
    }
);
