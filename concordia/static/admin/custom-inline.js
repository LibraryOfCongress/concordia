/* global jQuery */

(function ($) {
    $(document).ready(function () {
        function displayCardTitle(element) {
            var objectId = element.val();
            $.ajax({
                url: '/admin/serialized_object/',
                data: {
                    model_name: 'Card',
                    object_id: objectId,
                    field_name: 'title',
                },
                dataType: 'json',
                success: function (data) {
                    var title = $(
                        "<strong><a href='/admin/card/" +
                            objectId +
                            "/change/'>" +
                            data.title +
                            '</a></strong>',
                    );
                    var strong = element.siblings('strong');
                    if (strong.length > 0) {
                        strong.children(':first').text(data.title);
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
