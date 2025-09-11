import {ConcordiaVisualization} from '../modules/concordia-visualization.js';

const colors = ['#FFFFFF', '#002347', '#E0F6FF', '#257DB1'];

document.addEventListener('DOMContentLoaded', () => {
    const assetStatusOverviewChart = new ConcordiaVisualization({
        name: 'asset-status-overview',
        canvasId: 'asset-status-overview',
        chartType: 'pie',
        title: 'Page Status (Active Campaigns)',
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
                            borderColor: 'black',
                            borderWidth: 2,
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
