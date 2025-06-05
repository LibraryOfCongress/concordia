import Chart from 'chart.js/auto';

/**
 * Destroys any existing chart on this canvas and draws a “blank” chart that
 * only renders the title and axes (no data). Returns the new Chart instance.
 *
 * @param {CanvasRenderingContext2D} context
 * @param {Object} options
 * @param {string} options.title - the chart’s title text
 * @param {string} options.xLabel - x-axis title
 * @param {string} options.yLabel - y-axis title
 * @param {string} [options.chartType] - Chart.js type (default: 'bar')
 */
export function renderEmptyChart(
    context,
    {title, xLabel, yLabel, chartType = 'bar'},
) {
    // If there’s already a chart on this canvas, destroy it:
    const existing = Chart.getChart(context.canvas);
    if (existing) {
        existing.destroy();
    }

    // Create a new empty chart
    return new Chart(context, {
        type: chartType,
        data: {
            labels: [], // no x-axis labels
            datasets: [], // no data
        },
        options: {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: title,
                },
                tooltip: {
                    enabled: false,
                },
                legend: {
                    display: false,
                },
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
        },
    });
}

/**
 * Draws a centered error message overlay on top of whatever’s already been
 * rendered on the chart canvas. This does *not* destroy or modify the chart;
 * it simply paints a translucent rectangle and places text in the middle.
 *
 * @param {CanvasRenderingContext2D} context
 * @param {string} message
 * @param {Object} [options]
 * @param {string} [options.backgroundColor] - CSS color for overlay (default: "rgba(255,255,255,0.6)")
 * @param {string} [options.textColor] - CSS color for text (default: "#a00")
 * @param {string} [options.font] - CSS font for text (default: "bold 16px sans-serif")
 */
export function renderErrorOverlay(
    context,
    message,
    {
        backgroundColor = 'rgba(255, 255, 255, 0.6)',
        textColor = '#a00',
        font = 'bold 16px sans-serif',
    } = {},
) {
    const {width, height} = context.canvas;

    // Draw a semi‐transparent rectangle
    context.save();
    context.fillStyle = backgroundColor;
    context.fillRect(0, 0, width, height);
    context.restore();

    // Draw the error text centered
    context.save();
    context.fillStyle = textColor;
    context.font = font;
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(message, width / 2, height / 2);
    context.restore();
}
