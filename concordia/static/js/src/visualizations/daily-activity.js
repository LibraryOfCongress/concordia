import {ConcordiaVisualization} from '../modules/concordia-visualization.js';

document.addEventListener('DOMContentLoaded', () => {
    const dailyActivityChart = new ConcordiaVisualization({
        name: 'daily-transcription-activity-last-28-days',
        canvasId: 'daily-activity',
        chartType: 'bar',
        title: 'Daily Transcription Activity (Last 28 Days)',
        xLabel: 'Date',
        yLabel: 'Transcriptions + Reviews',
        buildDataset: (payload) => {
            return {
                data: {
                    labels: payload.labels,
                    datasets: payload.transcription_datasets,
                },
                options: {
                    scales: {
                        x: {
                            stacked: true,
                            ticks: {
                                callback: function (value, index) {
                                    // Show only every 4th tick starting at index 3 (i.e., the 4th day)
                                    return (index - 3) % 4 === 0
                                        ? this.getLabelForValue(index)
                                        : '';
                                },
                                autoSkip: false,
                            },
                        },
                        y: {
                            stacked: true,
                        },
                    },
                    plugins: {
                        legend: {
                            display: false,
                        },
                    },
                },
            };
        },
    });

    dailyActivityChart.render();
});
