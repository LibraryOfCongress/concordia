import React, {useEffect, useRef} from 'react';
import OpenSeadragon from 'openseadragon';
import 'openseadragon-filtering';
import screenfull from 'screenfull';

import {prefixUrl, contactUrl} from '../config.js';
import ViewerControls from './Controls';
import ImageFilters from './ImageFilters';
import KeyboardHelpModal from './KeyboardHelpModal';

/**
 * Viewer
 *
 * Mounts an OpenSeadragon instance, wires up UI controls and filter panels,
 * and exposes a fullscreen toggle. Cleans up the viewer on unmount.
 *
 * Behavior:
 * - Initializes OpenSeadragon with filtering support and common UI buttons
 * - On "open" event, recenters via viewport.goHome(true)
 * - On "open-failed", logs an error and shows an alert with a contact URL
 * - Stores the live OSD instance on window.seadragonViewer for external use
 * - Destroys the OSD instance during cleanup to avoid leaks
 *
 * Dependencies:
 * - Requires the "openseadragon-filtering" plugin to be imported once
 * - Uses the "screenfull" library for fullscreen where available
 *
 * @param {string} imageUrl - Source image URL used by OpenSeadragon.
 * @param {Function} onLayoutHorizontal - Callback to switch to horizontal layout.
 * @param {Function} onLayoutVertical - Callback to switch to vertical layout.
 * @returns {JSX.Element}
 */
export default function Viewer({
    imageUrl,
    onLayoutHorizontal,
    onLayoutVertical,
}) {
    const viewerRef = useRef(null);
    const osdViewerRef = useRef(null);

    useEffect(() => {
        if (!viewerRef.current || !imageUrl) return;

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

        window.seadragonViewer = osdViewerRef.current;

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
        <>
            <ViewerControls
                onLayoutHorizontal={onLayoutHorizontal}
                onLayoutVertical={onLayoutVertical}
                toggleFullscreen={toggleFullscreen}
            />
            <ImageFilters osdViewerRef={osdViewerRef} />
            <KeyboardHelpModal />
            <div
                id="asset-image"
                ref={viewerRef}
                className="h-100 bg-dark d-print-none w-100"
            ></div>
        </>
    );
}
