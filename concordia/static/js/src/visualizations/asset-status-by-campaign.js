import {ConcordiaVisualization} from 'concordia-visualization';

const colors = ['#FFFFFF', '#002347', '#E0F6FF', '#257DB1'];

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
                borderColor: 'black',
                borderWidth: 2,
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
