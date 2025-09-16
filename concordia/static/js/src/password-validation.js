import $ from 'jquery';

$(function () {
    var requirements = [
        {
            id: 'pw-length',
            text: 'At least 8 characters long',
            test: function (index) {
                return index.length >= 8;
            },
        },
        {
            id: 'pw-uppercase',
            text: '1 or more uppercase characters',
            test: function (index) {
                return index.match(/[A-Z]/);
            },
        },
        {
            id: 'pw-digits',
            text: '1 or more digits',
            test: function (index) {
                return index.match(/\d/);
            },
        },
        {
            id: 'pw-special',
            text: '1 or more special characters',
            test: function (index) {
                return index.match(/[^\d\sa-z]/i);
            },
        },
    ];
    var $password1 = $('#id_password1,#id_new_password1').removeAttr('title');
    var $requirementsList = $password1
        .siblings('.form-text')
        .find('ul')
        .addClass('list-unstyled')
        .empty();

    for (const request of requirements) {
        $('<li>')
            .attr('id', request.id)
            .text(request.text)
            .appendTo($requirementsList);
    }

    $password1.on('input change', function () {
        var currentValue = this.value;
        var validity = true;

        for (const request of requirements) {
            var li = document.getElementById(request.id);

            if (request.test(currentValue)) {
                li.className = 'text-success';
            } else {
                li.className = 'text-warning';
                validity = false;
            }
        }

        if (validity) {
            this.removeAttribute('aria-invalid');
            this.setCustomValidity('');
        } else {
            this.setAttribute('aria-invalid', 'true');
            this.setCustomValidity(
                'Your password does not meet the requirements',
            );
        }
    });
});
