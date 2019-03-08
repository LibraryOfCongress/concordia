import {$} from './utils/dom.js';

import {
    html,
    text,
    list,
    mount,
    unmount,
    setChildren,
    setAttr,
    List
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

export class MetadataPanel {
    /* Displays deep metadata for an asset inside a modal dialog */

    constructor(asset) {
        this.campaignMetadata = new CampaignMetadataDetails(
            'Campaign',
            asset.campaign
        );
        this.projectMetadata = new MetadataDetails('Project', asset.project);
        this.itemMetadata = new ItemMetadataDetails('Item', asset.item);

        this.el = html(
            'div',
            this.campaignMetadata,
            this.projectMetadata,
            this.itemMetadata
        );
    }
}

class MetadataDetails {
    constructor(sectionName, initialData) {
        this.el = html('details', {open: true}, [
            html('summary.h3', [
                text(`${sectionName}: `),
                html('span.title', text(initialData.title))
            ]),
            html('div.details-body')
        ]);
    }
    update(data) {
        $('.details-body', this.el).innerText = data.description || '';
    }
}

class CampaignMetadataDetails extends MetadataDetails {
    constructor(sectionName, initialData) {
        super(sectionName, initialData);

        this.relatedLinkTable = new RelatedLinkTable();
    }

    onmount() {
        mount(this.el, this.relatedLinkTable);
    }

    onunmount() {
        unmount(this.el, this.relatedLinkTable);
    }

    update(data) {
        super.update(data);

        this.relatedLinkTable.update(data.related_links);
    }
}

class RelatedLinkTableRow {
    constructor() {
        this.el = html('tr', html('th'), html('td'));
    }
    update(relatedLink) {
        this.el.querySelector('th').textContent = relatedLink.title;
        setChildren(
            this.el.querySelector('td'),
            html('a', {href: relatedLink.url}, text(relatedLink.url))
        );
    }
}

class RelatedLinkTable {
    constructor() {
        this.tbody = list('tbody', RelatedLinkTableRow);
        this.el = html(
            'table.related-links.table-sm',
            {hidden: true},
            html('caption', text('Related Links')),
            this.tbody
        );
    }
    update(data) {
        this.tbody.update(data);
        setAttr(this.el, {hidden: data.length < 1});
    }
}

class ItemMetadataDetails extends MetadataDetails {
    constructor(sectionName, initialData) {
        super(sectionName, initialData);

        this.featuredMetadata = new FeaturedMetadata();
        this.rawMetadataDisplay = new RawMetadataDisplay();
    }

    onmount() {
        mount(this.el, this.featuredMetadata);
        mount(this.el, this.rawMetadataDisplay);
    }

    onunmount() {
        unmount(this.el, this.featuredMetadata);
        unmount(this.el, this.rawMetadataDisplay);
    }

    update(data) {
        super.update(data);

        this.featuredMetadata.update(data.metadata.item || {});
        this.rawMetadataDisplay.update(data.metadata);
    }
}

class RawMetadataDisplay {
    constructor() {
        this.el = html(
            'details',
            html('summary', text('Raw Metadata')),
            html('pre.raw-metadata')
        );
    }
    update(data) {
        // TODO: JSON key sorting, highlighting, URL -> link conversion, etc.?
        this.el.querySelector('pre').innerText = !data
            ? ''
            : JSON.stringify(data, null, 2);
    }
}

class FeaturedMetadata extends List {
    constructor() {
        super('ul.list-unstyled.metadata-list', FeaturedMetadataEntry);
    }
    update(data) {
        const FEATURED_KEYS = [
            'dates',
            'contributor_names',
            'subject_headings'
        ];

        let featured = Object.entries(data)
            .filter(([key]) => FEATURED_KEYS.indexOf(key) >= 0)
            // We'll sort the list after filtering because mapping will convert
            // the keys to display titles:
            .sort(
                (a, b) =>
                    FEATURED_KEYS.indexOf(a[0]) - FEATURED_KEYS.indexOf(b[0])
            )
            .map(([key, value]) => {
                let values = [];

                // value can be a string, an array of strings, or an array of
                // objects. We have not yet needed to handle unnested objects or
                // arrays with mixed data-types but the code below attempts to
                // be defensive in the latter case.
                if (Array.isArray(value)) {
                    value.forEach(i => {
                        if (typeof i == 'string') {
                            values.push(i);
                        } else {
                            values.push(...Object.keys(i));
                        }
                    });
                } else {
                    values.push(value);
                }

                return [this.makeTitleFromKey(key), values];
            });

        super.update(featured);
    }

    makeTitleFromKey(key) {
        return key.replace('_', ' ');
    }
}

class FeaturedMetadataEntry {
    /*
        This is a nested list entry which will be given data in arrays of
        (title, list of strings) elements
     */

    constructor() {
        this.values = list('ul', Li);
        this.title = html('h2.title');
        this.el = html('li', this.title, this.values);
    }
    update([title, values]) {
        this.title.textContent = title;
        this.values.update(values);
    }
}

class Li {
    constructor() {
        this.el = html('li');
    }
    update(data) {
        this.el.textContent = data;
    }
}
