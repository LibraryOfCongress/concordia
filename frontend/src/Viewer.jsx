import React, {useEffect, useRef} from 'react';
import OpenSeadragon from 'openseadragon';
import screenfull from 'screenfull';
import debounce from 'lodash.debounce';

import {prefixUrl, contactUrl} from './config.js';

export default function Viewer({
    imageUrl,
    onLayoutHorizontal,
    onLayoutVertical,
}) {
    const viewerRef = useRef(null);
    const osdViewerRef = useRef(null);

    useEffect(() => {
        if (!viewerRef.current) return;

        osdViewerRef.current = OpenSeadragon({
            element: viewerRef.current,
            prefixUrl: prefixUrl,
            tileSources: {
                type: 'image',
                url: `${imageUrl}?canvas`,
            },
            gestureSettingsTouch: {
                pinchRotate: true,
            },
            showNavigator: true,
            showRotationControl: true,
            showFlipControl: true,
            zoomInButton: 'viewer-zoom-in',
            zoomOutButton: 'viewer-zoom-out',
            homeButton: 'viewer-home',
            rotateLeftButton: 'viewer-rotate-left',
            rotateRightButton: 'viewer-rotate-right',
            flipButton: 'viewer-flip',
            crossOriginPolicy: 'Anonymous',
            drawer: 'canvas',
            defaultZoomLevel: 0,
            homeFillsView: false,
        });

        // Go to home view after open (workaround for OpenSeadragon viewport init)
        osdViewerRef.current.addHandler('open', () => {
            setTimeout(() => {
                osdViewerRef.current.viewport.goHome(true);
            }, 0);
        });

        osdViewerRef.current.addHandler('open-failed', () => {
            console.error('Unable to display image');
            alert(`Unable to display image. Contact us at ${contactUrl}`);
        });

        return () => {
            if (osdViewerRef.current) {
                osdViewerRef.current.destroy();
            }
        };
    }, [imageUrl]);

    const toggleFullscreen = (e) => {
        e.preventDefault();
        if (!screenfull.isEnabled) return;
        if (screenfull.isFullscreen) {
            screenfull.exit();
        } else {
            screenfull.request(viewerRef.current);
        }
    };

    return (
        <div
            id="viewer-column"
            className="ps-0 d-flex align-items-stretch bg-dark d-print-block flex-column"
        >
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
            <div
                id="image-filters"
                className="m-1 text-center d-print-none collapse"
            >
                <hr className="m-0" />
                <ul
                    className="d-inline-flex mt-1 btn-group nav nav-tabs"
                    role="tablist"
                >
                    <li className="nav-item" role="presentation">
                        <button
                            id="viewer-gamma"
                            className="btn btn-dark nav-link active"
                            title="Adjust gamma"
                            data-bs-toggle="tab"
                            data-bs-target="#gamma-filter"
                            role="tab"
                        >
                            Brightness
                        </button>
                    </li>
                    <li className="nav-item" role="presentation">
                        <button
                            id="viewer-invert"
                            className="btn btn-dark nav-link"
                            title="Invert colors"
                            data-bs-toggle="tab"
                            data-bs-target="#invert-filter"
                            role="tab"
                        >
                            Invert
                        </button>
                    </li>
                    <li className="nav-item" role="presentation">
                        <button
                            id="viewer-threshold"
                            className="btn btn-dark nav-link"
                            title="Adjust threshold"
                            data-bs-toggle="tab"
                            data-bs-target="#threshold-filter"
                            role="tab"
                        >
                            Contrast
                        </button>
                    </li>
                </ul>
                <div className="btn-group m-1">
                    <button
                        id="viewer-reset"
                        className="btn"
                        title="Reset all filters"
                    >
                        Reset All
                    </button>
                </div>
                <div id="filter-tabs" className="tab-content">
                    <div
                        id="gamma-filter"
                        className="tab-pane pt-1 ps-3 show active"
                        role="tabpanel"
                    >
                        <form
                            id="gamma-form"
                            className="d-flex align-items-center"
                            onSubmit={(e) => {
                                e.preventDefault();
                            }}
                        >
                            <div className="row ms-0 me-3 number-input">
                                <div className="col p-1">
                                    <input
                                        type="number"
                                        id="gamma"
                                        name="gamma"
                                        min="0"
                                        max="5"
                                        step="0.01"
                                        defaultValue="1.00"
                                    />
                                    <label
                                        className="visually-hidden"
                                        htmlFor="gamma"
                                    >
                                        Gamma
                                    </label>
                                </div>
                                <div className="col p-0 filter-buttons">
                                    <div className="row m-0">
                                        <button
                                            id="gamma-up"
                                            type="button"
                                            className="arrow-button"
                                        >
                                            <span className="fas fa-chevron-up" />
                                            <span className="visually-hidden">
                                                Increase
                                            </span>
                                        </button>
                                    </div>
                                    <div className="row m-0">
                                        <button
                                            id="gamma-down"
                                            type="button"
                                            className="arrow-button"
                                        >
                                            <span className="fas fa-chevron-down" />
                                            <span className="visually-hidden">
                                                Decrease
                                            </span>
                                        </button>
                                    </div>
                                </div>
                            </div>
                            <input
                                type="range"
                                id="gamma-range"
                                name="gamma-range"
                                min="0"
                                max="5"
                                step="0.01"
                                defaultValue="1.00"
                                className="filter-slider flex-grow-1"
                            />
                            <label
                                className="visually-hidden"
                                htmlFor="gamma-range"
                            >
                                Gamma
                            </label>
                            <input
                                type="reset"
                                className="btn btn-link underline-link fw-bold"
                                defaultValue="Reset filter"
                            />
                        </form>
                    </div>
                    <div
                        id="invert-filter"
                        className="tab-pane pt-2"
                        role="tabpanel"
                        style={{backgroundColor: 'white'}}
                    >
                        <form
                            id="invert-form"
                            onSubmit={(e) => {
                                e.preventDefault();
                            }}
                            className="d-flex justify-content-center"
                        >
                            <label className="ms-2 align-middle">Off</label>
                            <div className="form-check form-switch custom-control-inline">
                                <input
                                    type="checkbox"
                                    id="invert"
                                    name="invert"
                                    className="form-check-input"
                                    role="switch"
                                />
                                <label
                                    className="form-check-label"
                                    htmlFor="invert"
                                >
                                    <span className="visually-hidden">
                                        Invert
                                    </span>
                                </label>
                            </div>
                            <label className="align-middle">On</label>
                        </form>
                    </div>
                    <div
                        id="threshold-filter"
                        className="tab-pane pt-1 ps-3"
                        role="tabpanel"
                    >
                        <form
                            id="threshold-form"
                            className="d-flex align-items-center"
                            onSubmit={(e) => {
                                e.preventDefault();
                            }}
                        >
                            <div className="row ms-0 me-3 number-input">
                                <div className="col p-1">
                                    <input
                                        type="number"
                                        id="threshold"
                                        name="threshold"
                                        min="0"
                                        max="255"
                                        step="1"
                                        defaultValue="0"
                                    />
                                    <label
                                        className="visually-hidden"
                                        htmlFor="threshold"
                                    >
                                        Threshold
                                    </label>
                                </div>
                                <div className="col p-0 filter-buttons">
                                    <div className="row m-0">
                                        <button
                                            id="threshold-up"
                                            type="button"
                                            className="arrow-button"
                                        >
                                            <span className="fas fa-chevron-up" />
                                            <span className="visually-hidden">
                                                Increase
                                            </span>
                                        </button>
                                    </div>
                                    <div className="row m-0">
                                        <button
                                            id="threshold-down"
                                            type="button"
                                            className="arrow-button"
                                        >
                                            <span className="fas fa-chevron-down" />
                                            <span className="visually-hidden">
                                                Decrease
                                            </span>
                                        </button>
                                    </div>
                                </div>
                            </div>
                            <input
                                type="range"
                                id="threshold-range"
                                name="threshold-range"
                                min="0"
                                max="255"
                                step="1"
                                defaultValue="0"
                                className="filter-slider flex-grow-1"
                            />
                            <label
                                className="visually-hidden"
                                htmlFor="threshold-range"
                            >
                                Threshold
                            </label>
                            <input
                                type="reset"
                                className="btn btn-link underline-link fw-bold"
                                defaultValue="Reset filter"
                            />
                        </form>
                    </div>
                </div>
            </div>
            <div
                id="keyboard-help-modal"
                className="modal"
                tabindex="-1"
                role="dialog"
            >
                <div
                    className="modal-dialog modal-dialog-centered"
                    role="document"
                >
                    <div className="modal-content">
                        <div className="modal-header">
                            <h5 className="modal-title">Keyboard Shortcuts</h5>
                            <button
                                type="button"
                                className="btn-close"
                                data-bs-dismiss="modal"
                                aria-label="Close"
                            ></button>
                        </div>
                        <div className="modal-body">
                            <h6>Viewer Shortcuts</h6>
                            <table className="table table-compact table-responsive">
                                <tr>
                                    <th>
                                        <kbd>w</kbd>, up arrow
                                    </th>
                                    <td>Scroll the viewport up</td>
                                </tr>
                                <tr>
                                    <th>
                                        <kbd>s</kbd>, down arrow
                                    </th>
                                    <td>Scroll the viewport down</td>
                                </tr>
                                <tr>
                                    <th>
                                        <kbd>a</kbd>, left arrow
                                    </th>
                                    <td>Scroll the viewport left</td>
                                </tr>
                                <tr>
                                    <th>
                                        <kbd>d</kbd>, right arrow{' '}
                                    </th>
                                    <td>Scroll the viewport right</td>
                                </tr>
                                <tr>
                                    <th>
                                        <kbd>0</kbd>
                                    </th>
                                    <td>
                                        Fit the entire image to the viewport
                                    </td>
                                </tr>
                                <tr>
                                    <th>
                                        <kbd>-</kbd>, <kbd>_</kbd>, Shift+
                                        <kbd>W</kbd>, Shift+Up arrow
                                    </th>
                                    <td>Zoom the viewport out</td>
                                </tr>
                                <tr>
                                    <th>
                                        <kbd>=</kbd>, <kbd>+</kbd>, Shift+
                                        <kbd>S</kbd>, Shift+Down arrow
                                    </th>
                                    <td>Scroll the viewport in</td>
                                </tr>
                                <tr>
                                    <th>
                                        <kbd>r</kbd>
                                    </th>
                                    <td>Rotate the viewport clockwise</td>
                                </tr>
                                <tr>
                                    <th>
                                        <kbd>R</kbd>
                                    </th>
                                    <td>
                                        Rotate the viewport counterclockwise
                                    </td>
                                </tr>
                                <tr>
                                    <th>
                                        <kbd>f</kbd>
                                    </th>
                                    <td>Flip the viewport horizontally</td>
                                </tr>
                            </table>
                        </div>
                        <div className="modal-footer">
                            <button
                                type="button"
                                className="btn btn-primary"
                                data-bs-dismiss="modal"
                            >
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            <div
                id="asset-image"
                ref={viewerRef}
                className="h-100 bg-dark d-print-none w-100"
            ></div>
        </div>
    );
}
