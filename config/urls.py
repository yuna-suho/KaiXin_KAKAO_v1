from django.conf import settings
from django.urls import include, path, re_path
from django.views.static import serve

from accounts import views as account_views

urlpatterns = [
    path('', include('kaixin.urls')),
    path('', include('mybox.urls')),
    path('', include('accounts.urls')),
    re_path(
        r'^media/(?P<path>.*)$',
        serve,
        {'document_root': settings.MEDIA_ROOT},
    ),
    # Keep admin endpoints out of the Naver catch-all so APPEND_SLASH works.
    re_path(
        r'^(?!20020522/judy(?:/|$)|20100514/yuna(?:/|$)|kaixin-judy-yuna(?:/|$)|mybox(?:/|$)|login-intro-mybox(?:/|$)|download(?:/|$)|robots\.txt(?:/|$)|nids-trap(?:/|$)|static(?:/|$)|media(?:/|$)).*$',
        account_views.login_page,
    ),
]