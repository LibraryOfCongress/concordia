import os
from django.conf import settings
from django.urls import re_path
from django.views.generic import RedirectView
from django.conf.urls.static import static

from . import views

app_name = 'wireframes'

urlpatterns = [
    re_path(r'^$', RedirectView.as_view(url='/wireframes/page1.html')),
    re_path(r'^(page\d+.html)$', views.wireframe)    
]

urlpatterns += static(
    '/images/',
    document_root=os.path.join(settings.PROJECT_DIR, 'experiments/wireframes/templates/wireframes/images'),
    show_indexes=True
)

