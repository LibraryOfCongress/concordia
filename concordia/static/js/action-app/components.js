import {$} from './utils/dom.js';

import {
    html,
    text
} from 'https://cdnjs.cloudflare.com/ajax/libs/redom/3.18.0/redom.es.min.js';

export class AssetTooltip {
    constructor() {
        this.el = html('.asset-tooltip.text-white.p-2', [
            html('.item-title'),
            html('.asset-title'),
            html('.difficulty-score-container', [
                text('Difficulty Score: '),
                html('span.difficulty-score')
            ])
        ]);
    }
    update(asset) {
        $('.item-title', this.el).innerText = asset.item.title;
        $('.asset-title', this.el).innerText = 'Image ' + asset.sequence;
        $('.difficulty-score', this.el).innerText = asset.difficulty;
    }
}
