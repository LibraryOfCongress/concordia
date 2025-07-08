import FilterTabNav from './FilterTabNav';
import GammaFilterForm from './GammaFilterForm';
import InvertFilterForm from './InvertFilterForm';
import ThresholdFilterForm from './ThresholdFilterForm';

export default function ImageFilters() {
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
                >
                    Reset All
                </button>
            </div>
            <div id="filter-tabs" className="tab-content">
                <GammaFilterForm />
                <InvertFilterForm />
                <ThresholdFilterForm />
            </div>
        </div>
    );
}
