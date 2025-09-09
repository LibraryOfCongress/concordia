import {useState, useEffect} from 'react';
import OpenSeadragon from 'openseadragon';
import debounce from 'lodash.debounce';

import FilterTabNav from './FilterTabNav';
import GammaFilterForm from './GammaFilterForm';
import InvertFilterForm from './InvertFilterForm';
import ThresholdFilterForm from './ThresholdFilterForm';

export default function ImageFilters({osdViewerRef}) {
    const [gamma, setGamma] = useState(1.0);
    const [invert, setInvert] = useState(false);
    const [threshold, setThreshold] = useState(0);

    const updateFilters = debounce(() => {
        if (!osdViewerRef.current) return;

        const filters = [];

        if (gamma !== 1 && gamma >= 0 && gamma <= 5) {
            filters.push(OpenSeadragon.Filters.GAMMA(gamma));
        }

        if (invert) {
            filters.push(OpenSeadragon.Filters.INVERT());
        }

        if (threshold > 0 && threshold <= 255) {
            filters.push(OpenSeadragon.Filters.THRESHOLDING(threshold));
        }

        osdViewerRef.current.setFilterOptions({
            filters: {processors: filters},
        });
    }, 100);

    useEffect(() => {
        updateFilters();
        return updateFilters.cancel; // cleanup debounce
    }, [gamma, invert, threshold]);

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
