/* global jQuery */

(function ($) {
    $(document).ready(function () {
        function displayCardTitle(element) {
            $.ajax({
                url: '/admin/serialized_object/',
                data: {
                    model_name: 'Card',
                    object_id: element.val(),
                    field_name: 'title',
                },
                dataType: 'json',
                success: function (data) {
                    var title = $('<strong>' + data.title + '</strong>');
                    var strong = element.siblings('strong');
                    if (strong.length > 0) {
                        strong.text(data.title);
                    } else {
                        element.siblings(':last').after(title);
                    }
                },
            });
        }

        $('input.vForeignKeyRawIdAdminField').on(
            'propertychange input',
            function () {
                displayCardTitle($(this));
            },
        );
    });
})(jQuery);
