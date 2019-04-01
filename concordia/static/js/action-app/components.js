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
        this.children = [
            html('summary.h3', [
                text(`${sectionName}: `),
                html('span.title', text(initialData.title))
            ]),
            html('div.details-body')
        ];
        this.el = html('details', {open: true}, this.children);
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

        this.children.push([this.featuredMetadata, this.rawMetadataDisplay]);
        setChildren(this.el, this.children);
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

class AssetListItem {
    constructor([assetListObserver]) {
        this.el = html('li', {
            class: 'asset rounded border',
            tabIndex: 0
        });

        assetListObserver.observe(this.el);
    }

    update(assetData) {
        // FIXME: adjust hidden state?

        let thumbnailUrl = assetData.thumbnailUrl;
        if (thumbnailUrl.indexOf('/iiif/') > 0) {
            // We'll adjust the IIIF image URLs not to return something larger
            // than we're going to use:
            // FIXME: this is an ugly, ugly kludge and should be replaced with something like https://www.npmjs.com/package/iiif-image
            thumbnailUrl = thumbnailUrl.replace(
                /([/]iiif[/].+[/]full)[/]pct:100[/](0[/]default.jpg)$/,
                '$1/!512,512/$2'
            );
        }

        this.el.id = assetData.id;
        this.el.classList.add('asset', 'rounded', 'border');
        this.el.dataset.image = thumbnailUrl;
        this.el.dataset.id = assetData.id;
        this.el.dataset.difficulty = assetData.difficulty;
        this.el.title = `${assetData.title} (${assetData.project.title})`;
    }
}

export class AssetList extends List {
    constructor(assets, callbacks) {
        // TODO: refactor this into a utility function
        let assetListObserver = new IntersectionObserver(entries => {
            entries
                .filter(i => i.isIntersecting)
                .forEach(entry => {
                    let target = entry.target;
                    target.style.backgroundImage = `url(${
                        target.dataset.image
                    })`;
                    assetListObserver.unobserve(target);
                });
        });

        /*
        This is used to lazy-load asset images. Note that we use the image
        as the background-image value because browsers load/unload invisible
        images from memory for us, unlike a regular <img> tag.
        */

        super('ul#asset-list.list-unstyled', AssetListItem, 'id', [
            assetListObserver
        ]);

        let assetOpenHandler = evt => {
            let target = evt.target;
            if (target && target.classList.contains('asset')) {
                callbacks.open(target);
                return false;
            }
        };

        this.el.addEventListener('click', assetOpenHandler);
        this.el.addEventListener('keydown', evt => {
            if (evt.key == 'Enter' || evt.key == ' ') {
                return assetOpenHandler(evt);
            }
        });

        this.setupTooltip(assets);
    }

    setupTooltip(assets) {
        /* Tooltips */
        let tooltip = new AssetTooltip();

        const handleTooltipShowEvent = evt => {
            let target = evt.target;
            if (target && target.classList.contains('asset')) {
                const asset = assets.get(target.dataset.id);
                tooltip.update(asset);
                mount(target, tooltip);
            }
        };

        const handleTooltipHideEvent = () => {
            if (tooltip.el.parentNode) {
                unmount(tooltip.el.parentNode, tooltip);
            }
        };

        // We want to handle both mouse hover events and keyboard/tap focus
        // changes. We'll use "focusin" which bubbles instead of “focus”, which
        // does not.

        this.el.addEventListener('mouseover', handleTooltipShowEvent);
        this.el.addEventListener('focusin', handleTooltipShowEvent);

        this.el.addEventListener('mouseout', handleTooltipHideEvent);
        this.el.addEventListener('focusout', handleTooltipHideEvent);

        $('#asset-list-thumbnail-size').addEventListener('input', evt => {
            this.el.style.setProperty(
                '--asset-thumbnail-size',
                evt.target.value + 'px'
            );
            this.attemptAssetLazyLoad();
        });
    }

    update(assets) {
        super.update(assets);
    }

    scrollToActiveAsset() {
        let activeAsset = $('.asset-active', this.el);
        if (activeAsset) {
            activeAsset.scrollIntoView({
                behavior: 'smooth',
                block: 'center',
                inline: 'nearest'
            });
        }
    }
}
