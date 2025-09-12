import {seadragonViewer} from './viewer.js';
import Split from 'split.js';

let pageSplit;
let contributeContainer = document.getElementById('contribute-container');
let ocrSection = document.getElementById('ocr-section');
let editorColumn = document.getElementById('editor-column');
let viewerColumn = document.getElementById('viewer-column');
let layoutColumns = ['#viewer-column', '#editor-column'];
let verticalKey = 'transcription-split-sizes-vertical';
let horizontalKey = 'transcription-split-sizes-horizontal';

let sizesVertical = localStorage.getItem(verticalKey);

if (sizesVertical) {
    sizesVertical = JSON.parse(sizesVertical);
} else {
    sizesVertical = [50, 50];
}

let sizesHorizontal = localStorage.getItem(horizontalKey);

if (sizesHorizontal) {
    sizesHorizontal = JSON.parse(sizesHorizontal);
} else {
    sizesHorizontal = [50, 50];
}

let splitDirection = localStorage.getItem('transcription-split-direction');

if (splitDirection) {
    splitDirection = JSON.parse(splitDirection);
} else {
    splitDirection = 'h';
}

function saveSizes(sizes) {
    let sizeKey;
    if (splitDirection == 'h') {
        sizeKey = horizontalKey;
        sizesHorizontal = sizes;
    } else {
        sizeKey = verticalKey;
        sizesVertical = sizes;
    }
    localStorage.setItem(sizeKey, JSON.stringify(sizes));
}

function saveDirection(direction) {
    localStorage.setItem(
        'transcription-split-direction',
        JSON.stringify(direction),
    );
}

function verticalSplit() {
    splitDirection = 'v';
    saveDirection(splitDirection);
    if (contributeContainer) {
        contributeContainer.classList.remove('flex-row');
        contributeContainer.classList.add('flex-column');
    }
    viewerColumn.classList.remove('h-100');
    if (ocrSection != undefined) {
        editorColumn.prepend(ocrSection);
    }

    return Split(layoutColumns, {
        sizes: sizesVertical,
        minSize: 100,
        gutterSize: 8,
        direction: 'vertical',
        elementStyle: function (dimension, size, gutterSize) {
            return {
                'flex-basis': 'calc(' + size + '% - ' + gutterSize + 'px)',
            };
        },
        gutterStyle: function (dimension, gutterSize) {
            return {
                'flex-basis': gutterSize + 'px',
            };
        },
        onDragEnd: saveSizes,
    });
}
function horizontalSplit() {
    splitDirection = 'h';
    saveDirection(splitDirection);
    if (contributeContainer) {
        contributeContainer.classList.remove('flex-column');
        contributeContainer.classList.add('flex-row');
    }
    viewerColumn.classList.add('h-100');
    if (ocrSection != undefined) {
        viewerColumn.append(ocrSection);
    }
    return Split(layoutColumns, {
        sizes: sizesHorizontal,
        minSize: 100,
        gutterSize: 8,
        elementStyle: function (dimension, size, gutterSize) {
            return {
                'flex-basis': 'calc(' + size + '% - ' + gutterSize + 'px)',
            };
        },
        gutterStyle: function (dimension, gutterSize) {
            return {
                'flex-basis': gutterSize + 'px',
            };
        },
        onDragEnd: saveSizes,
    });
}

if (contributeContainer && seadragonViewer) {
    if (splitDirection == 'v') {
        pageSplit = verticalSplit();
    } else {
        pageSplit = horizontalSplit();
    }

    document
        .getElementById('viewer-layout-horizontal')
        .addEventListener('click', function () {
            if (splitDirection != 'h') {
                if (pageSplit != undefined) {
                    pageSplit.destroy();
                }
                pageSplit = horizontalSplit();
                setTimeout(function () {
                    // Some quirk in the viewer makes this
                    // sometimes not work depending on
                    // the rotation, unless it's delayed.
                    // Less than 10ms didn't reliable work.
                    seadragonViewer.viewport.zoomTo(1);
                }, 10);
            }
        });

    document
        .getElementById('viewer-layout-vertical')
        .addEventListener('click', function () {
            if (splitDirection != 'v') {
                if (pageSplit != undefined) {
                    pageSplit.destroy();
                }
                pageSplit = verticalSplit();
                setTimeout(function () {
                    seadragonViewer.viewport.zoomTo(1);
                }, 10);
            }
        });
}
