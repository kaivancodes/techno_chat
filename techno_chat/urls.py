from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static

from backoffice_engine import views
from backoffice_engine import admin_views
urlpatterns = [
    path("admin/",   admin.site.urls),

    # User
    path("",         RedirectView.as_view(pattern_name="login", permanent=False)),
    path("login/",   views.login_view,   name="login"),
    path("logout/",        views.logout_view,        name="logout"),

    path("home/",    views.home_view,    name="home"),
    path("about/",   views.about_view,   name="about_us"),
    path("profile/", views.profile_view, name="profile"),

    # Files
    path("files/",        views.file_list_view,   name="file_list"),
    path("files/upload/", views.upload_file_view,  name="upload_file"),

    # Chat
    path("chat/",                          views.chat_list_view,     name="chat_list"),
    path("chat/new/",                      views.create_session_view, name="create_session"),
    path("chat/<int:session_id>/",         views.chat_view,          name="chat"),
    path("chat/<int:session_id>/send/",    views.chat_send_view,     name="chat_send"),

    path('chat/page-render/', views.page_render_view, name='page_render'),

    # Admin
    path("admin-login/", admin_views.admin_login_view, name="admin_login"),
    path("admin-register/", admin_views.admin_register_view, name="admin_register"),
    path("admin-profile/", admin_views.admin_profile_view, name="admin_profile"),
    path("admin-dashboard/", admin_views.admin_dashboard_view, name="admin_dashboard"),
    path("admin-new-contributor/", admin_views.admin_new_contributor_view, name="admin_new_contributor"),
    path("admin-logout/", admin_views.admin_logout_view, name="admin_logout"),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
