/* global jQuery */

(function ($) {
    $(document).ready(function () {
        function updateRelatedField(element) {
            var modelName = element.data('modelName');
            var objectId = element.data('objectId');
            var fieldName = element.data('fieldName');
            var url = '/admin/update_related_field/';

            $.ajax({
                url: url,
                data: {
                    model_name: modelName,
                    object_id: objectId,
                    field_name: fieldName,
                },
                dataType: 'json',
                success: function (data) {
                    element.val(data.value);
                },
            });
        }

        $('input.vForeignKeyRawIdAdminField').on('click', function () {
            var relatedField = $(this).siblings('.related-widget-wrapper');

            if (relatedField.length > 0) {
                updateRelatedField(relatedField.find('input'));
            }
        });
    });
})(jQuery);
