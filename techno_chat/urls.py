from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from backoffice_engine import views

urlpatterns = [
    path("admin/",   admin.site.urls),

    # Auth
    path("",         views.login_view,   name="login"),
    path("login/",   views.login_view,   name="login_page"),
    path("logout/",        views.logout_view,        name="logout"),
    path("admin-logout/", views.admin_logout_view,  name="admin_logout"),

    # Files
    path("files/",        views.file_list_view,   name="file_list"),
    path("files/upload/", views.upload_file_view,  name="upload_file"),

    # Chat
    path("chat/",                          views.chat_list_view,     name="chat_list"),
    path("chat/new/",                      views.create_session_view, name="create_session"),
    path("chat/<int:session_id>/",         views.chat_view,          name="chat"),
    path("chat/<int:session_id>/send/",    views.chat_send_view,     name="chat_send"),

    # ADD these to urls.py

    path("home/",    views.home_view,    name="home"),
    path("about/",   views.about_view,   name="about_us"),
    path("profile/", views.profile_view, name="profile"),

    path('chat/page-render/', views.page_render_view, name='page_render'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)