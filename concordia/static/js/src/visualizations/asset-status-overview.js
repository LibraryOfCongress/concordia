import {ConcordiaVisualization} from 'concordia-visualization';

const colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0'];

document.addEventListener('DOMContentLoaded', () => {
    const assetStatusOverviewChart = new ConcordiaVisualization({
        name: 'asset-status-overview',
        canvasId: 'asset-status-overview',
        chartType: 'pie',
        title: 'Asset Status (All Active Campaigns)',
        xLabel: '',
        yLabel: '',
        buildDataset: (payload) => {
            return {
                data: {
                    labels: payload.status_labels,
                    datasets: [
                        {
                            data: payload.total_counts,
                            backgroundColor: colors,
                        },
                    ],
                },
                options: {
                    scales: {
                        // We don't want scales on a pie chart
                        x: {display: false},
                        y: {display: false},
                    },
                },
            };
        },
    });

    assetStatusOverviewChart.render();
});
