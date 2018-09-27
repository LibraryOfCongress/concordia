/* global $ Cookies */

(function() {
    /*
        Configure jQuery to use CSRF tokens automatically — see
        https://docs.djangoproject.com/en/2.1/ref/csrf/#setting-the-token-on-the-ajax-request
    */

    var CSRFCookie = Cookies.get('csrfcookie');

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
