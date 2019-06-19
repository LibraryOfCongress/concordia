/* global CodeMirror prettier prettierPlugins django */

(function($) {
    var $bodyRow = $('.field-description');
    $bodyRow.find('label').remove();

    var preview = $(
        '<iframe id="id_description_preview" class="container"></iframe>'
    )
        // Firefox and, reportedly, Safari have a quirk where the <iframe> body
        // is not correctly available until it “loads” the blank page:
        .on('load', function() {
            var frameDocument = this.contentDocument;
            frameDocument.open();
            frameDocument.write(
                '<html><body><main>Loading…</main></body></html>'
            );
            frameDocument.close();

            var previewTemplate = document.querySelector(
                'template#preview-head'
            ).content;

            previewTemplate.childNodes.forEach(node => {
                frameDocument.head.appendChild(
                    frameDocument.importNode(node, true)
                );
            });

            queueUpdate();
        })
        .insertAfter('#id_description')
        .get(0);

    var editor = CodeMirror.fromTextArea(
        document.getElementById('id_description'),
        {
            mode: {
                name: 'xml',
                htmlMode: true
            },
            lineNumbers: true,
            highlightFormatting: true,
            indentUnit: 4,
            lineWrapping: true
        }
    );

    var queuedUpdate;

    editor.on('change', queueUpdate);

    function queueUpdate() {
        if (queuedUpdate) {
            window.cancelAnimationFrame(queuedUpdate);
        }
        queuedUpdate = window.requestAnimationFrame(updatePreview);
    }

    function updatePreview() {
        var main = preview.contentDocument.body.querySelector('main');
        if (main) {
            main.innerHTML = editor.getValue();
        }
    }

    $('<button class="button">Run Prettier</button>')
        .prependTo('.field-description')
        .on('click', function(event) {
            event.preventDefault();
            var pretty = prettier.format(editor.getValue(), {
                parser: 'html',
                plugins: prettierPlugins,
                printWidth: 120,
                tabWidth: 4
            });

            editor.setValue(pretty);
            queueUpdate();

            return false;
        });
})(django.jQuery);
