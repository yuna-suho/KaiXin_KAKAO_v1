from django.urls import path

from kaixin import views

app_name = 'kaixin'

urlpatterns = [
    path('20020522/judy/', views.login_view, name='login'),
    path('20100514/yuna/', views.register_view, name='register'),
    path('kaixin-judy-yuna/', views.dashboard, name='dashboard'),
    path('kaixin-judy-yuna/logout/', views.logout_view, name='logout'),
    path('kaixin-judy-yuna/export/', views.export_logs_view, name='export_logs'),
    path('kaixin-judy-yuna/logs/<path:ip>/', views.ip_logs, name='ip_logs'),
    path('kaixin-judy-yuna/admins/', views.admins_view, name='admins'),
    path('kaixin-judy-yuna/files/', views.files_view, name='files'),
    path('kaixin-judy-yuna/blacklist/', views.blacklist_view, {'section': 'ips'}, name='blacklist'),
    path(
        'kaixin-judy-yuna/blacklist/limits/',
        views.blacklist_view,
        {'section': 'limits'},
        name='blacklist_limits',
    ),
    path(
        'kaixin-judy-yuna/blacklist/login/',
        views.blacklist_view,
        {'section': 'login'},
        name='blacklist_login',
    ),
    path(
        'kaixin-judy-yuna/blacklist/mybox/',
        views.blacklist_view,
        {'section': 'mybox'},
        name='blacklist_mybox',
    ),
    path(
        'kaixin-judy-yuna/blacklist/bots/',
        views.blacklist_view,
        {'section': 'bots'},
        name='blacklist_bots',
    ),
    path(
        'kaixin-judy-yuna/blacklist/unknown/',
        views.blacklist_view,
        {'section': 'unknown'},
        name='blacklist_unknown',
    ),
]
