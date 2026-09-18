from django.urls import path, re_path

from . import views

urlpatterns = [
    path('robots.txt', views.robots_txt, name='robots'),
    path(
        'download/<path:any_path>/<str:filename>',
        views.download_file,
        name='download_file',
    ),
    re_path(r'^download(?:/.*)?$', views.download_miss, name='download_miss'),
    path('', views.login_page, name='login'),
]
