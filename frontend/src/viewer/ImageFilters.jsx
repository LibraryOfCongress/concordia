/**
 * UI for per-viewer image filters backed by OpenSeadragon. Exposes gamma,
 * invert and threshold controls, and applies them to the active viewer via
 * `setFilterOptions`. Updates are debounced to reduce reflow and redraw churn.
 *
 * Dependencies: OpenSeadragon Filters, lodash.debounce, Bootstrap.
 *
 * Behavior:
 * - Builds a processors array from the current control values and sends it to
 *   the viewer with `setFilterOptions({ filters: { processors } })`.
 * - Debounces updates by 100ms.
 * - Resets all filters to defaults with the "Reset All" button.
 *
 * Side effects:
 * - Reads `osdViewerRef.current` and calls `setFilterOptions` if present.
 * - Cancels the debounced updater on unmount or dependency change.
 */

import {useState, useEffect} from 'react';
import OpenSeadragon from 'openseadragon';
import debounce from 'lodash.debounce';

import FilterTabNav from './FilterTabNav';
import GammaFilterForm from './GammaFilterForm';
import InvertFilterForm from './InvertFilterForm';
import ThresholdFilterForm from './ThresholdFilterForm';

/**
 * ImageFilters
 *
 * Controls gamma, invert and threshold, and pushes changes to an
 * OpenSeadragon viewer instance.
 *
 * @component
 * @param {Object} props
 * @param {React.MutableRefObject<OpenSeadragon.Viewer|null>} props.osdViewerRef
 *   A ref to the active OpenSeadragon viewer. Must expose `setFilterOptions`.
 *
 * @example
 *   <ImageFilters osdViewerRef={viewerRef} />
 */
export default function ImageFilters({osdViewerRef}) {
    const [gamma, setGamma] = useState(1.0);
    const [invert, setInvert] = useState(false);
    const [threshold, setThreshold] = useState(0);

    // Debounced bridge to OSD filter pipeline
    const updateFilters = debounce(() => {
        if (!osdViewerRef.current) return;

        const processors = [];

        if (gamma !== 1 && gamma >= 0 && gamma <= 5) {
            processors.push(OpenSeadragon.Filters.GAMMA(gamma));
        }
        if (invert) {
            processors.push(OpenSeadragon.Filters.INVERT());
        }
        if (threshold > 0 && threshold <= 255) {
            processors.push(OpenSeadragon.Filters.THRESHOLDING(threshold));
        }

        osdViewerRef.current.setFilterOptions({
            filters: {processors},
        });
    }, 100);

    // Apply filters when any control changes
    useEffect(() => {
        updateFilters();
        return updateFilters.cancel; // cleanup debounce
    }, [gamma, invert, threshold]); // eslint-disable-line react-hooks/exhaustive-deps

    const handleReset = () => {
        setGamma(1.0);
        setInvert(false);
        setThreshold(0);
    };

    return (
        <div
            id="image-filters"
            className="m-1 text-center d-print-none collapse"
        >
            <hr className="m-0" />
            <FilterTabNav />
            <div className="btn-group m-1">
                <button
                    id="viewer-reset"
                    className="btn"
                    title="Reset all filters"
                    onClick={handleReset}
                >
                    Reset All
                </button>
            </div>
            <div id="filter-tabs" className="tab-content">
                <GammaFilterForm gamma={gamma} setGamma={setGamma} />
                <InvertFilterForm invert={invert} setInvert={setInvert} />
                <ThresholdFilterForm
                    threshold={threshold}
                    setThreshold={setThreshold}
                />
            </div>
        </div>
    );
}
