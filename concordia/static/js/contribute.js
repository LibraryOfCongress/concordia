$( document ).ready(function() {
  if ( window.location.href.indexOf( "#tab-tag" ) > -1 ) {
    $( '#nav-pill-tag' ).tab( 'show' );
  }
  sessionStorage.setItem('show_message', 'false');

  $( 'input[type="submit"]' ).click(function() {
    sessionStorage.setItem('show_message', 'true');
    });
});
