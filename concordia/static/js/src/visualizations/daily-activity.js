import {ConcordiaVisualization} from 'concordia-visualization';

document.addEventListener('DOMContentLoaded', () => {
    const dailyActivityChart = new ConcordiaVisualization({
        name: 'daily-transcription-activity-by-campaign',
        canvasId: 'daily-transcription-activity-by-campaign',
        chartType: 'bar',
        title: 'Daily Transcription Activity by Campaign (Last 7 Days)',
        xLabel: 'Date',
        yLabel: 'Transcriptions + Reviews',
        buildDataset: (payload) => {
            return {
                data: {
                    labels: payload.labels,
                    datasets: payload.transcription_datasets,
                },
            };
        },
    });

    dailyActivityChart.render();
});
