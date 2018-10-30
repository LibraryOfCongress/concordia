/* global $ Cookies screenfull */
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
}

function displayMessage(level, message, uniqueId) {
    displayHtmlMessage(level, document.createTextNode(message), uniqueId);
}

function isOutdatedBrowser() {
    if (typeof CSS == 'undefined' || !CSS.supports) {
        return true;
    }
    return !CSS.supports('display: flex');
}

$(function() {
    if (isOutdatedBrowser()) {
        theMessage =
            'You are using an outdated browser. This website fully supports the current ' +
            'version of every major browser ' +
            '(Microsoft Edge, Google Chrome, Mozilla Firefox, and Apple Safari). See ' +
            'our <a href="/help-center/#headingTwelve">browser support policy</a> ' +
            'for more information.';

        displayHtmlMessage('danger', theMessage);
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

$.ajax({url: '/account/ajax-status/', method: 'GET', cache: true}).done(
    function(data) {
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
    }
);

$.ajax({url: '/account/ajax-messages/', method: 'GET'}).done(function(data) {
    if (data.messages) {
        data.messages.forEach(function(message) {
            displayMessage(message.level, message.message);
        });
    }
});
