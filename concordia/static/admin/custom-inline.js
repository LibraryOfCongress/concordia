/* global jQuery */

(function ($) {
    function triggerChangeOnField(win, chosenId) {
        var element = document.getElementById(win.name);

        $.ajax({
            url: '/admin/serialized_object/',
            data: {
                model_name: 'Card',
                object_id: chosenId,
                field_name: 'title',
            },
            dataType: 'json',
            success: function (data) {
                const newContent = document.createTextNode(data.title);
                var a = document.createElement('a');
                a.href = '/admin/card/' + chosenId + '/change/';
                a.append(newContent);
                var newStrong = document.createElement('strong');
                newStrong.append(a);
                var strong = element.parentNode.querySelector('strong');
                if (strong) {
                    strong.replaceWith(newStrong);
                } else {
                    element.parentNode.append(newStrong);
                }
            },
        });
    }

    $(document).ready(function () {
        // https://stackoverflow.com/a/33937138/10320488
        window.ORIGINAL_dismissRelatedLookupPopup =
            window.dismissRelatedLookupPopup;
        window.dismissRelatedLookupPopup = function (win, chosenId) {
            window.ORIGINAL_dismissRelatedLookupPopup(win, chosenId);
            triggerChangeOnField(win, chosenId);
        };
    });
})(jQuery);
