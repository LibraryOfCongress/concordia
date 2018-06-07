// $( document ).ready(function() {

// });

//Make the DIV element draggagle:
dragElement(document.getElementById(("contribute-box")));

function dragElement(elmnt) {
  var pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;
  if (document.getElementById(elmnt.id + "-tabs")) {
    /* if present, the header is where you move the DIV from:*/
    document.getElementById(elmnt.id + "-tabs").onmousedown = dragMouseDown;
  } else {
    /* otherwise, move the DIV from anywhere inside the DIV:*/
    elmnt.onmousedown = dragMouseDown;
  }

  function dragMouseDown(e) {
    e = e || window.event;
    // get the mouse cursor position at startup:
    pos3 = e.clientX;
    pos4 = e.clientY;
    document.onmouseup = closeDragElement;
    // call a function whenever the cursor moves:
    document.onmousemove = elementDrag;
  }

  function elementDrag(e) {
    e = e || window.event;
    // calculate the new cursor position:
    pos1 = pos3 - e.clientX;
    pos2 = pos4 - e.clientY;
    pos3 = e.clientX;
    pos4 = e.clientY;
    // set the element's new position:
    // Need if statemements to keep on screen
    elmnt.style.top = (elmnt.offsetTop - pos2) + "px";
    elmnt.style.left = (elmnt.offsetLeft - pos1) + "px";
  }

  function closeDragElement() {
    /* stop moving when mouse button is released:*/
    document.onmouseup = null;
    document.onmousemove = null;
  }
}

// $('.dropup #transcription-percent li a').click(function(e) {
//   var target = e;
//   target.preventDefault();
//   if ( target.attr('id','status-0') ) {
//     $('#status_id').val(0);
//     $('#status-0').attr('active');
//   };
//   else if ( target.attr('id','status-25') ) {
//     $('#status_id').val(25);
//     $('#status-25').attr('active');
//   };
//   else if ( target.attr('id','status-50') ) {
//     $('#status_id').val(50);
//     $('#status-50').attr('active');
//   };
//   else if ( target.attr('id','status-75') ) {
//     $('#status_id').val(75);
//     $('#status-75').attr('active');
//   }; else {
//     $('#status_id').val(100);
//     $('#status-100').attr('active');
//   };
//   document.getElementById('contribute-form').submit();
// });

// $('#contribute-form').submit(function() {
//   alert(document.getElementById('status_id').value())
// });
// $('.dropup #status_id').click(function() {
//   var target = e.id;
//   // var target = $(this)[0];
//   var val = target.parent().val();
//   // var val = $(target).parent().val();
//   // var status = document.getElementById('status_id');
//   alert(val.val());
// });
