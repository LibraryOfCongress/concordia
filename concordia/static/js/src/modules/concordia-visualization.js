import Chart from 'chart.js/auto';
import {renderEmptyChart, renderErrorOverlay} from './visualization-errors.js';
import {generateAccessibleColors} from './accessible-colors.js';

const defaultAspectRatios = {
    pie: '1 / 1',
    doughnut: '1 / 1',
    radar: '1 / 1',
    bar: '2 / 1',
    line: '2 / 1',
};

export class ConcordiaVisualization {
    /**
     * @param {Object} config
     * @param {string} config.name
     *   The slug used to fetch `/api/visualization/<name>/`.
     * @param {string} config.canvasId
     *   The ID of the <canvas> element where the chart will be drawn.
     * @param {string} [config.chartType="bar"]
     *   The Chart.js chart type (e.g. "bar", "line", "pie", etc.).
     * @param {string} config.title
     *   The title to show on top of the chart (used both for real data and error case).
     * @param {string} [config.xLabel]
     *   The x-axis title (optional-if omitted, no x-axis label is shown).
     * @param {string} [config.yLabel]
     *   The y-axis title (optional-if omitted, no y-axis label is shown).
     * @param {Function} config.buildDataset
     *   A callback `(payload) => { data, [options] }` which receives the raw JSON payload
     *   and must return an object containing:
     *     - `data`: a valid Chart.js `data` object (`{ labels: [...], datasets: [...] }`), and
     *     - (optionally) `options`: partial Chart.js `options` you want to merge on top of the default.
     * @param {Object} [config.chartOptions]
     *   Any additional Chart.js options to merge into the final `options` object
     *   (will be deep-merged after `buildDataset(...).options`).
     * @param {string} [config.pageBackgroundColor="#fff"]
     *   The color of the page's background. Used to create contrasting colors
     * @param {number} [config.minContrast] - Minimum contrast between colors on the chart
     * @param {string} [config.aspectRatio]
     *   CSS aspect ratio. Default is based on chartType, as defined in defaultAspectRatios
     */
    constructor({
        name,
        canvasId,
        chartType = 'bar',
        title,
        xLabel = '',
        yLabel = '',
        buildDataset,
        chartOptions = {},
        pageBackgroundColor = '#fff',
        minContrast = 4.5,
        aspectRatio,
    }) {
        if (
            !name ||
            !canvasId ||
            !title ||
            typeof buildDataset !== 'function'
        ) {
            throw new Error(
                'ConcordiaVisualization requires: name, canvasId, title, and buildDataset()',
            );
        }

        this.name = name;
        this.canvasId = canvasId;
        this.chartType = chartType;
        this.title = title;
        this.xLabel = xLabel;
        this.yLabel = yLabel;
        this.buildDataset = buildDataset;
        this.chartOptions = chartOptions;
        this.pageBackgroundColor = pageBackgroundColor;
        this.minContrast = minContrast;

        if (aspectRatio) {
            this._cssAspectRatio = aspectRatio;
        } else {
            // Use the default if none provided, or failback to 2-to-1
            this._cssAspectRatio =
                defaultAspectRatios[this.chartType] ?? '2 / 1';
        }
    }

    /**
     * Fetches `/api/visualization/<name>/`, handles errors, and renders the chart.
     * Call this once the DOM is ready.
     */
    async render() {
        const canvas = document.getElementById(this.canvasId);
        if (!canvas) {
            console.error(
                `ConcordiaVisualization: Canvas ID '${this.canvasId}' not found.`,
            );
            return;
        }

        // Set accessibility attributes
        canvas.tabIndex = 0;
        canvas.setAttribute('role', 'img');
        canvas.setAttribute('aria-label', this.title);

        // Set aspectRatio on wrapper and make sure canvas fills it
        const wrapper = canvas.parentNode;
        wrapper.style.aspectRatio = this._cssAspectRatio;
        canvas.style.width = '100%';
        canvas.style.height = '100%';

        const context = canvas.getContext('2d');

        let resp;
        try {
            resp = await fetch(`/api/visualization/${this.name}/`);
        } catch (error) {
            console.error(
                `ConcordiaVisualization: Network error fetching '${this.name}':`,
                error,
            );
            this._handleError(context, 'No data available');
            return;
        }

        if (!resp.ok) {
            console.error(
                `ConcordiaVisualization: HTTP ${resp.status} for '${this.name}'.`,
            );
            this._handleError(context, 'No data available');
            return;
        }

        // If a chart already exists on this canvas, destroy it
        Chart.getChart(canvas)?.destroy();

        let payload;
        try {
            payload = await resp.json();
        } catch (error) {
            console.error(
                `ConcordiaVisualization: Failed to parse JSON for '${this.name}':`,
                error,
            );
            this._handleError(context, 'No data available');
            return;
        }

        let data,
            userOptions = {};
        try {
            // Let user-supplied buildDataset transform payload into { data, [options] }
            const result = this.buildDataset(payload);
            data = result.data;
            userOptions = result.options || {};
        } catch (error) {
            console.error(
                `ConcordiaVisualization: buildDataset threw for '${this.name}':`,
                error,
            );
            this._handleError(context, 'No data available');
            return;
        }

        if (!data || typeof data !== 'object') {
            console.error(
                `ConcordiaVisualization: buildDataset must return an object with a 'data' property for '${this.name}'.`,
            );
            this._handleError(context, 'No data available');
            return;
        }

        // Auto-generate accessible colors only if none provided
        const originalDatasets = data.datasets || [];
        if (originalDatasets.length > 0) {
            const hasExplicit = originalDatasets.some(
                (ds) =>
                    ds.backgroundColor !== undefined ||
                    ds.borderColor !== undefined,
            );
            if (!hasExplicit) {
                if (originalDatasets.length > 1) {
                    const colors = generateAccessibleColors(
                        originalDatasets.length,
                        this.pageBackgroundColor,
                        this.minContrast,
                    );
                    data.datasets = originalDatasets.map((ds, index) => ({
                        ...ds,
                        backgroundColor: colors[index],
                        borderColor: colors[index],
                        borderWidth: ds.borderWidth ?? 1,
                    }));
                } else {
                    const count = data.labels?.length || 0;
                    const colors = generateAccessibleColors(
                        count,
                        this.pageBackgroundColor,
                        this.minContrast,
                    );
                    data.datasets = [
                        {
                            ...originalDatasets[0],
                            backgroundColor: colors,
                            borderColor: colors,
                            borderWidth: originalDatasets[0].borderWidth ?? 1,
                        },
                    ];
                }
            }
        }

        // Merge options: default -> userOptions -> this.chartOptions
        const finalOptions = ConcordiaVisualization._deepMerge(
            {},
            ConcordiaVisualization._defaultOptions(
                this.title,
                this.xLabel,
                this.yLabel,
            ),
            userOptions,
            this.chartOptions,
        );

        // Create the Chart.js chart
        let chart = new Chart(context, {
            type: this.chartType,
            data: data,
            options: finalOptions,
        });

        // If CSV URL exists in payload, create a link below the canvas
        if (payload.csv_url) {
            // wrapper is the <section>, container is the <div>
            // Insert link after the wrapper, but within the outer container
            const container = wrapper.parentNode;
            const link = document.createElement('a');
            link.href = payload.csv_url;
            link.textContent = 'Download data as CSV';
            link.classList.add('visualization-data-link');
            link.setAttribute('target', '_blank');
            link.setAttribute('rel', 'noopener noreferrer');
            container.append(link);
        }

        // Create a hidden live region for announcing the current slice/bar
        const live = document.createElement('div');
        live.id = `${this.canvasId}-live`;
        live.setAttribute('aria-live', 'polite');
        Object.assign(live.style, {
            position: 'absolute',
            width: '1px',
            height: '1px',
            margin: '-1px',
            padding: 0,
            border: 0,
            clip: 'rect(0 0 0 0)',
        });
        canvas.parentNode.insertBefore(live, canvas.nextSibling);

        // Wire up keyboard navigation
        const meta = chart.getDatasetMeta(0).data; // first dataset's elements
        let elementIndex = 0;

        // helper to update tooltip and live text
        function highlight(index) {
            // build an array of every datasetIndex at this index
            const elements = chart.data.datasets
                .map((_unusedValue, datasetIndex) => ({datasetIndex, index}))
                .filter(({datasetIndex}) => {
                    // skip if that dataset doesn't actually have a bar at this index
                    return !!chart.getDatasetMeta(datasetIndex).data[index];
                });

            // get a tooltip-friendly position from one of the elements
            const {x, y} = chart
                .getDatasetMeta(elements[0].datasetIndex)
                .data[index].tooltipPosition();

            // activate them all
            chart.setActiveElements(elements);
            chart.tooltip.setActiveElements(elements, {x, y});
            chart.update();

            // update the live region:
            live.textContent =
                `${chart.data.labels[index]} - ` +
                elements
                    .map(({datasetIndex}) => {
                        const ds = chart.data.datasets[datasetIndex];
                        return `${ds.label}: ${ds.data[index]}`;
                    })
                    .join(', ');
        }

        // initialize on focus
        canvas.addEventListener('focus', () => {
            elementIndex = 0;
            highlight(elementIndex);
        });

        // arrow-key handling
        canvas.addEventListener('keydown', (event) => {
            if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
                elementIndex = (elementIndex + 1) % meta.length;
            } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
                elementIndex = (elementIndex - 1 + meta.length) % meta.length;
            } else {
                return; // ignore other keys
            }
            event.preventDefault();
            highlight(elementIndex);
        });
    }

    /**
     * Instance-private helper: destroy any existing chart on this canvas,
     * draw a blank chart with title + axes, and overlay an error message.
     */
    _handleError(context, message) {
        renderEmptyChart(context, {
            title: this.title,
            xLabel: this.xLabel,
            yLabel: this.yLabel,
            chartType: this.chartType,
        });
        renderErrorOverlay(context, message);

        // insert a visible error message under the canvas, for UAs (such as screenreaders)
        // that can't handle the canvas
        const canvas = context.canvas;
        const container = canvas.parentNode;
        const alert = document.createElement('div');
        alert.setAttribute('role', 'alert');
        alert.classList.add('visually-hidden');
        alert.textContent = message;
        container.insertBefore(alert, canvas.nextSibling);
    }

    /**
     * Default Chart.js options (title + axes) for a "real" chart.
     * Individual visualizations can override or extend these via userOptions.
     */
    static _defaultOptions(title, xLabel, yLabel) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: title,
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                },
                legend: {
                    position: 'top',
                    labels: {
                        boxWidth: 12,
                        padding: 8,
                    },
                },
            },
            interaction: {
                mode: 'index',
                intersect: false,
            },
            scales: {
                x: {
                    title: {
                        display: !!xLabel,
                        text: xLabel,
                    },
                },
                y: {
                    beginAtZero: true,
                    title: {
                        display: !!yLabel,
                        text: yLabel,
                    },
                },
            },
        };
    }

    /**
     * Simple deep-merge of multiple objects.
     * Later sources overwrite earlier keys.
     */
    static _deepMerge(target, ...sources) {
        for (const source of sources) {
            if (source && typeof source === 'object') {
                for (const [key, value] of Object.entries(source)) {
                    // Skip any attempt to assign "__proto__" or "constructor"
                    if (key === '__proto__' || key === 'constructor') {
                        continue;
                    }

                    if (
                        value &&
                        typeof value === 'object' &&
                        !Array.isArray(value) &&
                        !(value instanceof HTMLElement)
                    ) {
                        if (!target[key] || typeof target[key] !== 'object') {
                            target[key] = {};
                        }
                        ConcordiaVisualization._deepMerge(target[key], value);
                    } else {
                        target[key] = value;
                    }
                }
            }
        }
        return target;
    }
}
