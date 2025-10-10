/* global prettier prettierPlugins django */

import {EditorState} from '@codemirror/state';
import {EditorView, basicSetup} from '@codemirror/view';
import {html} from '@codemirror/lang-html';
import {markdown} from '@codemirror/lang-markdown';

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

                const previewTemplate = document.querySelector(
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
                main.innerHTML = converter(view.state.doc.toString());
            }
        }

        let queuedUpdate;
        function queueUpdate() {
            if (queuedUpdate) {
                cancelAnimationFrame(queuedUpdate);
            }
            queuedUpdate = requestAnimationFrame(updatePreview);
        }

        const language = flavor === 'html' ? html() : markdown();

        const updateListener = EditorView.updateListener.of((update) => {
            if (update.docChanged) queueUpdate();
        });

        const state = EditorState.create({
            doc: textarea.value,
            extensions: [basicSetup, language, updateListener],
        });

        const view = new EditorView({
            state,
            parent: textarea.parentElement,
        });

        textarea.style.display = 'none'; // hide the original

        $('<button class="button">Run Prettier</button>')
            .prependTo($formRow)
            .on('click', function (event) {
                event.preventDefault();

                $formRow.find('.errornote').remove();

                try {
                    var pretty = prettier.format(view.state.doc.toString(), {
                        parser: flavor,
                        plugins: prettierPlugins,
                        printWidth: 120,
                        tabWidth: 4,
                    });

                    view.dispatch({
                        changes: {
                            from: 0,
                            to: view.state.doc.length,
                            insert: pretty,
                        },
                    });
                    queueUpdate();
                } catch (error) {
                    $('<p class="errornote">').text(error).appendTo($formRow);
                    console.error(error);
                }
            });
    };
})(django.jQuery);
