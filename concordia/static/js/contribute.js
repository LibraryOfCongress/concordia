$('#nav-pill-transcription, #nav-pill-tag, #nav-pill-discussion').click(function( e ) {
  if ( e.target.id == 'nav-pill-transcription' ) {
    $('#status_id,#status-id-label,input.btn-primary').removeClass('d-none');
  } else if ( e.target.id == 'nav-pill-discussion' ) {
  	$('#status_id,#status-id-label,input.btn-primary').addClass('d-none');
  }
  else {
    $('#status_id,#status-id-label').addClass('d-none');
    }
});
