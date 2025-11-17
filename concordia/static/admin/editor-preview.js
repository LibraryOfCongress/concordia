/* global CodeMirror prettier prettierPlugins django */

(function ($) {
    window.setupCodeMirror = function (textarea, flavor) {
        var converter;
        switch (flavor) {
            case 'html': {
                converter = (input) => input;
                break;
            }
            case 'markdown': {
                var md = new window.remarkable.Remarkable({html: true});
                converter = (input) => md.render(input);
                break;
            }
            default: {
                throw 'Unknown code flavor: ' + flavor;
            }
        }

        var $formRow = $(textarea).parents('.form-row').first();
        $formRow.addClass('codemirror-with-preview');

        var preview = $('<iframe>')
            // Firefox and, reportedly, Safari have a quirk where the <iframe> body
            // is not correctly available until it “loads” the blank page:
            .on('load', function () {
                var frameDocument = this.contentDocument;
                frameDocument.open();
                frameDocument.write(
                    '<html><body><main>Loading…</main></body></html>',
                );
                frameDocument.close();

                var previewTemplate = document.querySelector(
                    'template#preview-head',
                ).content;

                for (const node of previewTemplate.childNodes) {
                    frameDocument.head.append(
                        frameDocument.importNode(node, true),
                    );
                }

                queueUpdate();
            })
            .insertAfter(textarea)
            .get(0);

        function updatePreview() {
            var main = preview.contentDocument.body.querySelector('main');
            if (main) {
                main.innerHTML = converter(editor.getValue());
            }
        }

        var editorMode = flavor;
        if (flavor == 'html') {
            // CodeMirror actually treats HTML as a subset of XML:
            editorMode = {
                name: 'xml',
                htmlMode: true,
            };
        }

        var editor = CodeMirror.fromTextArea(textarea, {
            mode: editorMode,
            lineNumbers: true,
            highlightFormatting: true,
            indentUnit: 4,
            lineWrapping: true,
        });

        var editorLineWidgets = [];

        var queuedUpdate;

        editor.on('change', queueUpdate);

        function queueUpdate() {
            if (queuedUpdate) {
                window.cancelAnimationFrame(queuedUpdate);
            }
            queuedUpdate = window.requestAnimationFrame(updatePreview);
        }

        $('<button class="button">Run Prettier</button>')
            .prependTo($formRow)
            .on('click', function (event) {
                event.preventDefault();

                $formRow.find('.errornote').remove();

                for (const widget of editorLineWidgets) {
                    editor.removeLineWidget(widget);
                }

                try {
                    var pretty = prettier.format(editor.getValue(), {
                        parser: flavor,
                        plugins: prettierPlugins,
                        printWidth: 120,
                        tabWidth: 4,
                    });

                    editor.setValue(pretty);
                    queueUpdate();
                } catch (error) {
                    $('<p class="errornote">').text(error).appendTo($formRow);

                    var lineWarning = document.createElement('div');
                    lineWarning.style.whiteSpace = 'nowrap';
                    lineWarning.style.overflow = 'hidden';

                    var icon = lineWarning.append(
                        document.createElement('span'),
                    );
                    icon.style.marginRight = '1rem';
                    icon.innerHTML = '⚠️';
                    lineWarning.append(document.createTextNode(error.message));

                    editorLineWidgets.push(
                        editor.addLineWidget(
                            error.loc.start.line - 1,
                            lineWarning,
                            {coverGutter: false, noHScroll: true},
                        ),
                    );
                }
            });
    };
})(django.jQuery);
