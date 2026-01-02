import React, {useLayoutEffect, useRef, useState} from 'react';
import Split from 'split.js';

import Editor from './editor/Editor';
import Viewer from './viewer/Viewer';
import OcrSection from './ocr/Section';

/**
 * @typedef {Object} AssetData
 * @property {number} id
 * @property {string} imageUrl
 * @property {Object} [transcription]
 *   Latest transcription object for the asset, or null if none.
 * @property {string} transcriptionStatus
 *   One of the server statuses used to choose UI state.
 * @property {number} registeredContributors
 * @property {Array<[string,string]>} languages
 *   Array of [isoCode, languageName] pairs used by OCR.
 * @property {boolean} undoAvailable
 * @property {boolean} redoAvailable
 */

/**
 * Split-pane layout for the transcription UI.
 *
 * Renders the image viewer on one side and the editor on the other,
 * with a draggable gutter. The split direction and pane sizes persist
 * to localStorage. When the direction changes, the viewer is nudged to
 * re-fit the image.
 *
 * Local storage keys:
 * - "transcription-split-sizes-vertical" for vertical sizes
 * - "transcription-split-sizes-horizontal" for horizontal sizes
 * - "transcription-split-direction" for the active direction
 *
 * @param {{assetData: AssetData, onTranscriptionUpdate?: (t: Object) => void}} props
 *   assetData: Data for the current asset.
 *   onTranscriptionUpdate: Callback when a new transcription is saved
 *   or loaded.
 */
export default function ViewerSplit({assetData, onTranscriptionUpdate}) {
    const contributeContainerRef = useRef(null);
    const editorColumnRef = useRef(null);

    const verticalKey = 'transcription-split-sizes-vertical';
    const horizontalKey = 'transcription-split-sizes-horizontal';
    const directionKey = 'transcription-split-direction';

    const [splitDirection, setSplitDirection] = useState(
        JSON.parse(localStorage.getItem(directionKey)) || 'h',
    );

    const [transcription, setTranscription] = useState(assetData.transcription);

    /**
     * Handle an updated transcription payload from child components.
     * Updates local state and forwards to the optional parent callback.
     *
     * @param {Object} updated
     */
    const handleTranscriptionUpdate = (updated) => {
        if (!updated?.text) {
            console.warn(
                'handleTranscriptionUpdate called with malformed object:',
                updated,
            );
            return;
        }
        setTranscription(updated);
        if (onTranscriptionUpdate) onTranscriptionUpdate(updated);
    };

    /**
     * Update only the transcription text field as the user types.
     *
     * @param {string} newText
     */
    const handleTranscriptionTextChange = (newText) => {
        setTranscription((prev) => ({
            ...prev,
            text: newText,
        }));
    };

    /**
     * Read persisted Split.js sizes or return the provided defaults.
     *
     * @param {string} key
     * @param {number[]} defaultSizes
     * @returns {number[]}
     */
    const getSizes = (key, defaultSizes) => {
        const sizes = localStorage.getItem(key);
        return sizes ? JSON.parse(sizes) : defaultSizes;
    };

    /**
     * Persist pane sizes for the current direction.
     *
     * @param {number[]} sizes
     */
    const saveSizes = (sizes) => {
        const key = splitDirection === 'h' ? horizontalKey : verticalKey;
        localStorage.setItem(key, JSON.stringify(sizes));
    };

    /**
     * Persist the active split direction.
     *
     * @param {'h'|'v'} dir
     */
    const saveDirection = (dir) => {
        localStorage.setItem(directionKey, JSON.stringify(dir));
    };

    /**
     * Create or recreate the Split.js instance whenever direction changes.
     * Cleans up on unmount. Uses flex-basis so panes respect the gutter size.
     */
    useLayoutEffect(() => {
        const sizes =
            splitDirection === 'h'
                ? getSizes(horizontalKey, [50, 50])
                : getSizes(verticalKey, [50, 50]);

        const splitInstance = Split(['#viewer-column', '#editor-column'], {
            sizes,
            minSize: 100,
            gutterSize: 8,
            direction: splitDirection === 'h' ? 'horizontal' : 'vertical',
            elementStyle: (dimension, size, gutterSize) => ({
                flexBasis: `calc(${size}% - ${gutterSize}px)`,
            }),
            gutterStyle: (dimension, gutterSize) => ({
                flexBasis: `${gutterSize}px`,
            }),
            onDragEnd: saveSizes,
        });

        return () => {
            splitInstance.destroy();
        };
    }, [splitDirection]);

    /**
     * Toggle between horizontal and vertical layouts.
     * Saves direction then requests the OpenSeadragon viewer to re-fit.
     *
     * @param {'h'|'v'} dir
     */
    const handleToggle = (dir) => {
        if (dir !== splitDirection) {
            setSplitDirection(dir);
            saveDirection(dir);
            setTimeout(() => {
                if (window.seadragonViewer?.viewport) {
                    window.seadragonViewer.viewport.zoomTo(1);
                }
            }, 10);
        }
    };

    return (
        <div className="viewer-split">
            <div
                id="contribute-container"
                ref={contributeContainerRef}
                className={`d-flex ${
                    splitDirection === 'h' ? 'flex-row' : 'flex-column'
                }`}
                style={{height: '100vh'}}
            >
                <div
                    id="viewer-column"
                    className="ps-0 d-flex align-items-stretch bg-dark d-print-block flex-column"
                >
                    <Viewer
                        imageUrl={assetData.imageUrl}
                        onLayoutHorizontal={() => handleToggle('h')}
                        onLayoutVertical={() => handleToggle('v')}
                    />
                    <OcrSection
                        assetId={assetData.id}
                        transcription={transcription}
                        onTranscriptionUpdate={handleTranscriptionUpdate}
                        languages={assetData.languages}
                    />
                </div>
                <div id="editor-column" ref={editorColumnRef}>
                    <Editor
                        assetId={assetData.id}
                        transcription={transcription}
                        transcriptionStatus={assetData.transcriptionStatus}
                        registeredContributors={
                            assetData.registeredContributors
                        }
                        undoAvailable={assetData.undoAvailable}
                        redoAvailable={assetData.redoAvailable}
                        onTranscriptionUpdate={handleTranscriptionUpdate}
                        onTranscriptionTextChange={
                            handleTranscriptionTextChange
                        }
                    />
                </div>
            </div>
        </div>
    );
}
