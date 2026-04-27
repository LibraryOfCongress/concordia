import React, {useEffect, useRef, useState} from 'react';
import OpenSeadragon from 'openseadragon';
import {initializeFiltering} from 'openseadragon-filters';
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
 * - Requires the "openseadragon-filters" plugin to be imported once
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
    const viewerRef = useRef(null); // For OSD
    const containerRef = useRef(null); // For Fullscreen wrapper
    const osdViewerRef = useRef(null);
    const filterPluginRef = useRef(null);

    // State to track fullscreen changes
    const [isFullscreen, setIsFullscreen] = useState(false);

    // Add listener for fullscreen changes
    useEffect(() => {
        const handler = () => {
            setIsFullscreen(screenfull.isFullscreen);
        };

        if (screenfull.isEnabled) {
            screenfull.on('change', handler);
        }

        return () => {
            if (screenfull.isEnabled) {
                screenfull.off('change', handler);
            }
        };
    }, []);

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

        // Initialize the plugin instance - filtering using the ESM method
        filterPluginRef.current = initializeFiltering(osdViewerRef.current);

        return () => {
            if (osdViewerRef.current) {
                osdViewerRef.current.destroy();
                osdViewerRef.current = null;
            }
            // Clear the plugin ref on unmount
            filterPluginRef.current = null;
        };
    }, [imageUrl]);

    const toggleFullscreen = (e) => {
        e.preventDefault();
        if (!screenfull.isEnabled) return;
        if (screenfull.isFullscreen) {
            screenfull.exit();
        } else {
            // Request fullscreen on the wrapper, not just the image
            screenfull.request(containerRef.current);
        }
    };

    return (
        <div
            ref={containerRef}
            className={`d-flex flex-column h-100 w-100 ${
                isFullscreen ? 'is-fullscreen' : ''
            }`}
            style={isFullscreen ? {backgroundColor: '#212529'} : {}}
        >
            <ViewerControls
                onLayoutHorizontal={onLayoutHorizontal}
                onLayoutVertical={onLayoutVertical}
                toggleFullscreen={toggleFullscreen}
            />
            <ImageFilters filterPluginRef={filterPluginRef} />
            <KeyboardHelpModal />
            <div
                id="asset-image"
                ref={viewerRef}
                className="flex-grow-1 bg-dark d-print-none w-100"
            ></div>
        </div>
    );
}
