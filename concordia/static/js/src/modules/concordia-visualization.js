import Chart from 'chart.js/auto';
import {renderEmptyChart, renderErrorOverlay} from 'visualization-errors';
import {generateAccessibleColors} from './accessible-colors.js';

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
        pageBackgroundColor = '#fff',
        minContrast = 4.5,
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

        // build a hidden HTML table of the same data for screen‐readers
        this._renderDataTable(data);

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

            // get a tooltip‐friendly position from one of the elements
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

        // arrow‐key handling
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
     * Build a DOM <table> from the Chart.js `data` object,
     * give it a visually‐hidden class, and insert it after the canvas.
     */
    _renderDataTable(data) {
        const canvas = document.getElementById(this.canvasId);
        const container = canvas.parentNode;

        const table = document.createElement('table');
        table.setAttribute('aria-label', `${this.title} data table`);
        table.classList.add('visually-hidden');

        // caption: include both axis labels
        const cap = document.createElement('caption');
        const xLabel = this.xLabel || 'Category';
        const yLabel = this.yLabel || (data.datasets[0]?.label ?? 'Value');
        cap.textContent = `${this.title} - "${yLabel}" by ${xLabel}`;
        table.append(cap);

        // header row: first cell = xLabel, then one <th> per dataset
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        const cornerTh = document.createElement('th');
        cornerTh.scope = 'col';
        cornerTh.textContent = xLabel;
        headerRow.append(cornerTh);

        for (const ds of data.datasets) {
            const th = document.createElement('th');
            th.scope = 'col';
            // if the dataset has a .label, use it; otherwise use the y-axis label
            th.textContent = ds.label || yLabel;
            headerRow.append(th);
        }

        thead.append(headerRow);
        table.append(thead);

        // body rows: one per label
        const tbody = document.createElement('tbody');
        for (const [index, label] of data.labels.entries()) {
            const tr = document.createElement('tr');

            // row header = the label
            const rowHeader = document.createElement('th');
            rowHeader.scope = 'row';
            rowHeader.textContent = label;
            tr.append(rowHeader);

            // then one <td> per dataset
            for (const ds of data.datasets) {
                const td = document.createElement('td');
                const value = ds.data[index];
                if (Array.isArray(value)) {
                    td.textContent = value.join(', ');
                } else {
                    td.textContent = String(value);
                }
                tr.append(td);
            }

            tbody.append(tr);
        }

        table.append(tbody);

        container.insertBefore(table, canvas.nextSibling);
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
