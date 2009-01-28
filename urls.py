from django.conf.urls.defaults import *
from django.contrib import admin
from django.conf import settings

admin.autodiscover()

urlpatterns = patterns(
    '',
    (r'^$', 'django.views.generic.simple.redirect_to', {'url': '/audio'}),
    (r'^audio/', include('menclave.aenclave.urls')),
    (r'^video/', include('menclave.venclave.urls')),
    #(r'^games/', include('menclave.genclave.urls')),
    (r'^admin/(.*)', admin.site.root),
)

if settings.DEBUG:
    urlpatterns += patterns(
        '',
        (r'^media/(?P<path>.*)$',
         'django.views.static.serve',
         {'document_root': settings.MEDIA_ROOT}),
    )