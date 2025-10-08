import $ from 'jquery';

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
