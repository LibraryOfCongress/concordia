/**
 * Controls the binarization threshold used by the image viewer filter.
 *
 * Behavior:
 * - Number input and range slider stay in sync.
 * - Up and down arrow buttons change the value by 1 within 0-255.
 * - Reset sets the threshold to 0.
 *
 * Accessibility:
 * - Inputs have associated labels with visually hidden text.
 * - Increment and decrement buttons include hidden text for screen readers.
 *
 * @param {number} threshold - Current threshold value in the range 0-255.
 * @param {Function} setThreshold - Setter to update the threshold.
 * @returns {JSX.Element}
 */
export default function ThresholdFilterForm({threshold, setThreshold}) {
    const handleNumberChange = (e) => {
        setThreshold(parseInt(e.target.value, 10));
    };

    const handleRangeChange = (e) => {
        setThreshold(parseInt(e.target.value, 10));
    };

    const handleReset = () => {
        setThreshold(0);
    };

    const stepUp = () => {
        setThreshold((prev) => Math.min(prev + 1, 255));
    };

    const stepDown = () => {
        setThreshold((prev) => Math.max(prev - 1, 0));
    };

    return (
        <div
            id="threshold-filter"
            className="tab-pane pt-1 ps-3"
            role="tabpanel"
        >
            <form
                id="threshold-form"
                className="d-flex align-items-center"
                onSubmit={(e) => e.preventDefault()}
                onReset={handleReset}
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
                            value={threshold}
                            onChange={handleNumberChange}
                        />
                        <label className="visually-hidden" htmlFor="threshold">
                            Threshold
                        </label>
                    </div>
                    <div className="col p-0 filter-buttons">
                        <div className="row m-0">
                            <button
                                id="threshold-up"
                                type="button"
                                className="arrow-button"
                                onClick={stepUp}
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
                                onClick={stepDown}
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
                    value={threshold}
                    onChange={handleRangeChange}
                    className="filter-slider flex-grow-1"
                />
                <label className="visually-hidden" htmlFor="threshold-range">
                    Threshold
                </label>
                <input
                    type="reset"
                    className="btn btn-link underline-link fw-bold"
                    value="Reset filter"
                />
            </form>
        </div>
    );
}
