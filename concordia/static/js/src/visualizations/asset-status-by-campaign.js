import {ConcordiaVisualization} from 'concordia-visualization';

const colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0'];

document.addEventListener('DOMContentLoaded', () => {
    const assetStatusByCampaignChart = new ConcordiaVisualization({
        name: 'asset-status-by-campaign',
        canvasId: 'asset-status-by-campaign',
        chartType: 'bar',
        title: 'Page Status by Campaign (Active Campaigns)',
        xLabel: 'Campaign',
        yLabel: 'Page Count',
        buildDataset: (payload) => {
            const fullNames = payload.campaign_names;
            const shortLabels = fullNames.map((name) =>
                name.length > 20 ? name.slice(0, 20) + '…' : name,
            );

            const statusKeys = Object.keys(payload.per_campaign_counts);
            const statusLabels = payload.status_labels;

            const datasets = statusKeys.map((key, index) => ({
                label: statusLabels[index],
                data: payload.per_campaign_counts[key],
                backgroundColor: colors[index],
            }));

            return {
                data: {
                    labels: shortLabels, // truncated names on the axis
                    datasets: datasets,
                },
                options: {
                    scales: {
                        x: {stacked: true},
                        y: {stacked: true, beginAtZero: true},
                    },
                    plugins: {
                        tooltip: {
                            // We want the full names on hover
                            callbacks: {
                                title: (tooltipItems) => {
                                    const campaignIndex =
                                        tooltipItems[0].dataIndex;
                                    return fullNames[campaignIndex];
                                },
                                label: (tooltipItem) => {
                                    const status = tooltipItem.dataset.label;
                                    const value = tooltipItem.parsed.y;
                                    return `${status}: ${value}`;
                                },
                            },
                        },
                    },
                },
            };
        },
    });

    assetStatusByCampaignChart.render();
});
