from django.contrib import admin
from backoffice_engine.models import User, UserProfile, File, ChatSession, ChatMessage, AdminUser, AdminProfile

admin.site.register(User)
admin.site.register(File)
admin.site.register(UserProfile)
admin.site.register(ChatSession)
admin.site.register(ChatMessage)
admin.site.register(AdminUser)
admin.site.register(AdminProfile)
admin.site.login_template = 'admin/admin_login.html'

admin.site.site_header = "TechnoChat Admin"
admin.site.site_title = "TechnoChat Portal"
admin.site.index_title = "Welcome to TechnoChat Dashboard"