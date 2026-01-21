/**
 * Gamma filter controls for the viewer.
 *
 * Purpose:
 * - Provide synchronized number and range inputs to adjust gamma.
 * - Offer step up/down buttons and a Reset filter control.
 *
 * Behavior:
 * - Value is clamped to [0, 5] and rounded to two decimals.
 * - onSubmit is prevented; onReset sets gamma to 1.0.
 * - Exposed ids for external hooks:
 *   #gamma-filter, #gamma-form, #gamma, #gamma-range, #gamma-up, #gamma-down.
 *
 * Accessibility:
 * - Visually hidden labels for inputs.
 * - Buttons include hidden Increase and Decrease text.
 *
 * Props:
 * @param {number} gamma - Current gamma value.
 * @param {(value:number)=>void} setGamma - Setter invoked on change.
 * @returns {JSX.Element}
 */
export default function GammaFilterForm({gamma, setGamma}) {
    const handleNumberChange = (e) => {
        const value = parseFloat(e.target.value);
        if (!isNaN(value)) setGamma(value);
    };

    const handleRangeChange = (e) => {
        const value = parseFloat(e.target.value);
        if (!isNaN(value)) setGamma(value);
    };

    const stepUp = () => {
        const newValue = Math.min(5, gamma + 0.01);
        setGamma(parseFloat(newValue.toFixed(2)));
    };

    const stepDown = () => {
        const newValue = Math.max(0, gamma - 0.01);
        setGamma(parseFloat(newValue.toFixed(2)));
    };

    const handleReset = () => {
        setGamma(1.0);
    };

    return (
        <div
            id="gamma-filter"
            className="tab-pane pt-1 ps-3 show active"
            role="tabpanel"
        >
            <form
                id="gamma-form"
                className="d-flex align-items-center"
                onSubmit={(e) => e.preventDefault()}
                onReset={handleReset}
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
                            value={gamma}
                            onChange={handleNumberChange}
                        />
                        <label className="visually-hidden" htmlFor="gamma">
                            Gamma
                        </label>
                    </div>
                    <div className="col p-0 filter-buttons">
                        <div className="row m-0">
                            <button
                                id="gamma-up"
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
                                id="gamma-down"
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
                    id="gamma-range"
                    name="gamma-range"
                    min="0"
                    max="5"
                    step="0.01"
                    value={gamma}
                    onChange={handleRangeChange}
                    className="filter-slider flex-grow-1"
                />
                <label className="visually-hidden" htmlFor="gamma-range">
                    Gamma
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
