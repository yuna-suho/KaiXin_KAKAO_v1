from django.urls import path, re_path

from mybox import views

app_name = 'mybox'

urlpatterns = [
    path('mybox/', views.image_viewer, name='viewer'),
    re_path(r'^mybox/.+$', views.image_viewer, name='viewer_any'),
    path('login-intro-mybox/', views.intro_image_viewer, name='intro_viewer'),
]
