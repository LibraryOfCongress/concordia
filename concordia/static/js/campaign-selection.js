/* global jQuery */

(function($) {
  
    $('input[type="checkbox"]').change(function () {
        
        if (this.checked) 
        {
       
            $("." + this.id).fadeIn('slow');
        }
        else 
            $("." + this.id).fadeOut('slow');
    });


})(jQuery);
