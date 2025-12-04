import $ from 'jquery';
import {getPages} from './recent-pages.js';

window.sortDateAscending = function () {
    var urlParameters = new URLSearchParams(window.location.search);
    urlParameters.set('order_by', 'date-ascending');
    getPages('?' + urlParameters.toString());
};
window.sortDateDescending = function () {
    var urlParameters = new URLSearchParams(window.location.search);
    urlParameters.set('order_by', 'date-descending');
    getPages('?' + urlParameters.toString());
};
$(document).ready(function () {
    let profilePage = document.getElementById('profile-page');
    let activeTab = profilePage?.dataset.activeTab;
    if (activeTab === 'recent') {
        getPages();
    }
    if (window.location.hash != '') {
        $('a[href="' + window.location.hash + '"]').click();
        if (window.location.hash == '#recent') {
            getPages();
        }
    }
});
// Disable form submissions, if there are invalid fields
(function () {
    window.addEventListener(
        'load',
        function () {
            // Fetch all the forms we want to apply custom Bootstrap validation styles to
            var forms = document.querySelectorAll('.needs-validation');
            for (const form of forms) {
                form.addEventListener('submit', (event) => {
                    $('#validation-confirmation').hide();
                    if (!form.checkValidity()) {
                        event.preventDefault();
                        event.stopPropagation();
                    }
                    form.classList.add('was-validated');
                });
            }
        },
        false,
    );
})();
