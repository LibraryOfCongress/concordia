/**
 * Viewer toolbar with layout, zoom, rotate, flip, filters, help and fullscreen.
 *
 * Purpose:
 * - Provide a consistent control strip for the image viewer.
 * - Emit layout events to the parent container.
 * - Expose stable button ids so external code can bind OpenSeadragon actions.
 *
 * Integration:
 * - The parent supplies handlers for layout changes and fullscreen:
 *   onLayoutHorizontal, onLayoutVertical, toggleFullscreen.
 * - Other buttons are bound by id at runtime by OpenSeadragon:
 *   #viewer-home, #viewer-zoom-in, #viewer-zoom-out,
 *   #viewer-rotate-left, #viewer-rotate-right, #viewer-flip.
 * - Bootstrap attributes handle the filters collapse and keyboard help modal.
 *
 * Accessibility:
 * - Buttons include title text. Icons add aria-label where needed.
 *
 * Usage:
 * <ViewerControls
 *   onLayoutHorizontal={() => setLayout('h')}
 *   onLayoutVertical={() => setLayout('v')}
 *   toggleFullscreen={handleFullscreen}
 * />
 */

import React from 'react';

/**
 * @param {Object} props
 * @param {function():void} props.onLayoutHorizontal
 *   Switch to horizontal layout.
 * @param {function():void} props.onLayoutVertical
 *   Switch to vertical layout.
 * @param {function():void} props.toggleFullscreen
 *   Enter or exit fullscreen mode for the viewer.
 * @returns {JSX.Element}
 */
export default function ViewerControls({
    onLayoutHorizontal,
    onLayoutVertical,
    toggleFullscreen,
}) {
    return (
        <div id="viewer-controls" className="m-1 text-center d-print-none">
            <div className="d-inline-flex justify-content-between">
                <div className="d-flex btn-group m-1">
                    <button
                        id="viewer-layout-vertical"
                        className="btn btn-dark viewer-control-button"
                        title="Vertical Layout"
                        onClick={onLayoutVertical}
                    >
                        <span className="fas fa-grip-lines"></span>
                    </button>
                    <button
                        id="viewer-layout-horizontal"
                        className="btn btn-dark"
                        title="Horizontal Layout"
                        onClick={onLayoutHorizontal}
                    >
                        <span className="fas fa-grip-lines-vertical"></span>
                    </button>
                </div>

                <div className="d-flex btn-group m-1">
                    <button
                        type="button"
                        id="viewer-home"
                        className="btn btn-dark viewer-control-button"
                        title="Fit Image to Viewport"
                    >
                        <span className="fas fa-compress"></span>
                    </button>
                </div>

                <div className="d-flex btn-group m-1">
                    <button
                        id="viewer-zoom-in"
                        className="btn btn-dark viewer-control-button"
                        title="Zoom In"
                    >
                        <span className="fas fa-search-plus"></span>
                    </button>
                    <button
                        id="viewer-zoom-out"
                        className="btn btn-dark"
                        title="Zoom Out"
                    >
                        <span className="fas fa-search-minus"></span>
                    </button>
                </div>

                <div className="d-flex btn-group m-1">
                    <button
                        id="viewer-rotate-left"
                        className="btn btn-dark viewer-control-button"
                        title="Rotate Left"
                    >
                        <span className="fas fa-undo"></span>
                    </button>
                    <button
                        id="viewer-rotate-right"
                        className="btn btn-dark viewer-control-button"
                        title="Rotate Right"
                    >
                        <span className="fas fa-redo"></span>
                    </button>
                </div>

                <div className="d-flex btn-group m-1">
                    <button
                        id="viewer-flip"
                        className="btn btn-dark viewer-control-button"
                        title="Flip"
                    >
                        <span className="fas fa-exchange-alt"></span>
                    </button>
                </div>

                <div className="d-flex btn-group m-1">
                    <button
                        type="button"
                        className="btn btn-dark extra-control-button"
                        title="Image Filters"
                        data-bs-toggle="collapse"
                        data-bs-target="#image-filters"
                    >
                        <span
                            className="fas fa-sliders-h"
                            aria-label="Image Filters"
                        ></span>
                    </button>
                </div>

                <div className="d-flex btn-group m-1">
                    <button
                        type="button"
                        id="viewer-fullscreen"
                        className="btn btn-dark extra-control-button"
                        title="View Full Screen"
                        onClick={toggleFullscreen}
                    >
                        <span className="fas fa-expand"></span>
                    </button>
                </div>

                <div className="d-flex btn-group m-1">
                    <button
                        type="button"
                        className="btn btn-dark extra-control-button"
                        title="Viewer keyboard shortcuts"
                        data-bs-toggle="modal"
                        data-bs-target="#keyboard-help-modal"
                    >
                        <span
                            className="fas fa-question-circle"
                            aria-label="Viewer keyboard shortcuts"
                        ></span>
                    </button>
                </div>
            </div>
        </div>
    );
}
