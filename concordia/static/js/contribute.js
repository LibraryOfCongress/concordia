$( document ).ready(function() {
  if ( window.location.href.indexOf( "#tab-tag" ) > -1 ) {
    $( '#nav-pill-tag' ).tab( 'show' );
  }
  $( 'input[type="submit"]' ).click(function() {
    sessionStorage.setItem('show_message', 'true');
    });
});
