$('#nav-pill-transcription, #nav-pill-tag, #nav-pill-discussion').mouseup(function() {
  if ( !$('#nav-pill-transcription').hasClass('active') ) {
    $('#status-id,#status-id-label').addClass('d-none');
  } else {
    $('#status-id,#status-id-label').removeClass('d-none');
    }
});