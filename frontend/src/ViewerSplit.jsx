import React, {useLayoutEffect, useRef, useState} from 'react';
import Split from 'split.js';

import Editor from './editor/Editor';
import Viewer from './viewer/Viewer';

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

    // Handle live typing
    const handleTranscriptionTextChange = (newText) => {
        setTranscription((prev) => ({
            ...prev,
            text: newText,
        }));
    };

    const getSizes = (key, defaultSizes) => {
        const sizes = localStorage.getItem(key);
        return sizes ? JSON.parse(sizes) : defaultSizes;
    };

    const saveSizes = (sizes) => {
        const key = splitDirection === 'h' ? horizontalKey : verticalKey;
        localStorage.setItem(key, JSON.stringify(sizes));
    };

    const saveDirection = (dir) => {
        localStorage.setItem(directionKey, JSON.stringify(dir));
    };

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
