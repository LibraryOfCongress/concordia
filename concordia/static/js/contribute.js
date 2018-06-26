$('#nav-pill-transcription, #nav-pill-tag, #nav-pill-discussion').click(function( e ) {
  if ( e.target.id == 'nav-pill-transcription' ) {
    $('#status_id, #status-id-label').removeClass('d-none');
  } else {
    $('#status_id,#status-id-label').addClass('d-none');
    }
});
