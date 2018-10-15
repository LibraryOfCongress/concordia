/* global jQuery */

(function($) {
    var requirements = [
        {
            id: 'pw-length',
            text: 'At least 8 characters long',
            test: function(i) {
                return i.length >= 8;
            }
        },
        {
            id: 'pw-uppercase',
            text: '1 or more uppercase characters',
            test: function(i) {
                return i.match(/[A-Z]/);
            }
        },
        {
            id: 'pw-digits',
            text: '1 or more digits',
            test: function(i) {
                return i.match(/[0-9]/);
            }
        },
        {
            id: 'pw-special',
            text: '1 or more special characters',
            test: function(i) {
                return i.match(/[^\s\da-z]/i);
            }
        }
    ];
    var $password1 = $('#id_password1,#id_new_password1').removeAttr('title');
    var $requirementsList = $password1
        .siblings('.form-text')
        .find('ul')
        .addClass('list-unstyled')
        .empty();

    requirements.forEach(function(req) {
        $('<li>')
            .attr('id', req.id)
            .text(req.text)
            .appendTo($requirementsList);
    });

    $password1.on('input change', function() {
        var currentVal = this.value;
        var validity = true;

        requirements.forEach(function(req) {
            var li = document.getElementById(req.id);

            if (req.test(currentVal)) {
                li.className = 'text-success';
            } else {
                li.className = 'text-warning';
                validity = false;
            }
        });

        if (validity) {
            this.removeAttribute('aria-invalid');
            this.setCustomValidity('');
        } else {
            this.setAttribute('aria-invalid', 'true');
            this.setCustomValidity(
                'Your password does not meet the requirements'
            );
        }
    });
})(jQuery);
