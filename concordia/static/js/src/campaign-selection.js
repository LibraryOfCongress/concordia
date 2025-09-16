import $ from 'jquery';

$(function () {
    const queryString = window.location.search;
    const urlParameters = new URLSearchParams(queryString);

    $('#tblTranscription tbody tr').each(function () {
        var rowID = $(this).find('.campaign').attr('id');

        if (rowID == urlParameters.get('campaign_slug')) {
            $(this).find('.campaign').css('font-weight', 'bold');
        } else {
            $(this).find('.campaign').attr('font-weight', 'normal');
        }
    });

    $('input[type="checkbox"]').change(function () {
        if (this.checked) {
            $('.' + this.id).fadeIn('slow');
        } else $('.' + this.id).fadeOut('slow');
    });
});
