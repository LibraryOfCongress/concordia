import Chart from 'chart.js/auto';
import {renderEmptyChart, renderErrorOverlay} from 'visualization-errors';

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
     *   The x-axis title (optional—if omitted, no x-axis label is shown).
     * @param {string} [config.yLabel]
     *   The y-axis title (optional—if omitted, no y-axis label is shown).
     * @param {Function} config.buildDataset
     *   A callback `(payload) => { data, [options] }` which receives the raw JSON payload
     *   and must return an object containing:
     *     - `data`: a valid Chart.js `data` object (`{ labels: [...], datasets: [...] }`), and
     *     - (optionally) `options`: partial Chart.js `options` you want to merge on top of the default.
     * @param {Object} [config.chartOptions]
     *   Any additional Chart.js options to merge into the final `options` object
     *   (will be deep‐merged after `buildDataset(...).options`).
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
        canvas.setAttribute('role', 'img');
        canvas.setAttribute('aria-label', this.title);

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
            // Let user‐supplied buildDataset transform payload into { data, [options] }
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
        new Chart(context, {
            type: this.chartType,
            data: data,
            options: finalOptions,
        });
    }

    /**
     * Instance‐private helper: destroy any existing chart on this canvas,
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
    }

    /**
     * Default Chart.js options (title + axes) for a "real" chart.
     * Individual visualizations can override or extend these via userOptions.
     */
    static _defaultOptions(title, xLabel, yLabel) {
        return {
            responsive: true,
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
