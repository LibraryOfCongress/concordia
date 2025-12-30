import $ from 'jquery';
import {Modal} from 'bootstrap';

function clearCache() {
    const keys = Object.keys(localStorage);
    for (const key of keys) {
        if (key.startsWith('campaign-')) {
            localStorage.removeItem(key);
        }
    }
}

function initCampaignTutorial() {
    const campaignData = document.getElementById('campaign-data');
    if (campaignData) {
        if (typeof Storage === 'undefined') return;

        const campaignSlug = campaignData.dataset.campaignSlug;
        const isAuthenticated =
            campaignData.dataset.userAuthenticated === 'true';
        const hasAsset = campaignData.dataset.hasAsset === 'true';
        if (campaignSlug) {
            const keyName = `campaign-${campaignSlug}`;
            const seen = localStorage.getItem(keyName);

            if (!seen) {
                if (!isAuthenticated) {
                    clearCache();
                }

                if (hasAsset) {
                    if (typeof window.setTutorialHeight === 'function') {
                        window.setTutorialHeight();
                    }

                    $(function () {
                        const modalElement =
                            document.getElementById('tutorial-popup');
                        const modal = new Modal(modalElement);
                        modal.show();
                    });

                    localStorage.setItem(keyName, 'true');
                }
            }
        } else if (!isAuthenticated) {
            clearCache();
        }
    }
}

document.addEventListener('DOMContentLoaded', initCampaignTutorial);

function setTutorialHeight() {
    let $carouselItems = $('#card-carousel .carousel-item');
    let heights = $carouselItems.map(function () {
        let height = $(this).height();
        if (height <= 0) {
            let firstChild = $(this).children[0];
            if (firstChild) {
                height = firstChild.offsetHeight + 48;
            } else {
                return 517.195;
            }
        }
        return height;
    });
    let maxHeight = Math.max.apply(this, heights);
    $carouselItems.height(maxHeight);
}

export {setTutorialHeight};

// Expose globally so inline HTML can see it
window.setTutorialHeight = setTutorialHeight;
