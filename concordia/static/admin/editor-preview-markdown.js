/* global Remarkable CodeMirror prettier prettierPlugins django */

(function($) {
    var md = new Remarkable({html: true});

    var $bodyRow = $('.field-body');
    $bodyRow.find('label').remove();

    var $bodyPreview = $('<div id="id_body_preview" class="container">');
    $bodyPreview.insertAfter('#id_body');

    var editor = CodeMirror.fromTextArea(document.getElementById('id_body'), {
        mode: 'markdown',
        lineNumbers: true,
        highlightFormatting: true,
        indentUnit: 4,
        lineWrapping: true
    });

    var queuedUpdate;

    editor.on('change', queueUpdate);

    function queueUpdate() {
        if (queuedUpdate) {
            window.cancelAnimationFrame(queuedUpdate);
        }
        queuedUpdate = window.requestAnimationFrame(updatePreview);
    }

    function updatePreview() {
        $bodyPreview.empty().html(md.render(editor.getValue()));
    }

    $('<button class="button">Run Prettier</button>')
        .prependTo('.field-body')
        .on('click', function(event) {
            event.preventDefault();
            var pretty = prettier.format(editor.getValue(), {
                parser: 'markdown',
                plugins: prettierPlugins,
                printWidth: 120,
                tabWidth: 4
            });

            editor.setValue(pretty);
            queueUpdate();

            return false;
        });

    updatePreview();
})(django.jQuery);
