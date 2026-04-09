from django.shortcuts import render, redirect
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate, login
from backoffice_engine.models import AdminUser
from backoffice_engine.admin_auth import create_admin


# =========================
# ADMIN LOGIN
# =========================
def admin_login_view(request):
    error = None

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        if not email or not password:
            error = "All fields are required."

        else:
            user = authenticate(request, username=email, password=password)

            if user is None:
                error = "Invalid email or password."
            elif not user.is_staff:
                error = "You do not have admin access."
            else:
                login(request, user)
                request.session['role'] = 'admin'
                
                # Check profile completion
                if hasattr(user, 'admin_profile') and not user.admin_profile.is_profile_complete:
                    return redirect('admin_profile')
                    
                return redirect('admin_dashboard')

    return render(request, "admin/admin_login.html", {"error": error})


# =========================
# ADMIN REGISTER
# =========================
def admin_register_view(request):
    error = None
    success = None

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        confirm = request.POST.get("confirm_password", "")

        if not email or not password or not confirm:
            error = "All fields are required."

        elif password != confirm:
            error = "Passwords do not match."

        elif AdminUser.objects.filter(email=email).exists():
            error = "Email id exists."

        else:
            try:
                create_admin(email, password)
                success = "Account created successfully! Redirecting in 3 seconds..."

            except ValidationError as e:
                error = e.message if hasattr(e, 'message') else str(e)

    return render(request, "admin/admin_register.html", {
        "error": error,
        "success": success
    })


# =========================
# ADMIN DASHBOARD (NEW)
# =========================
from django.contrib.auth.decorators import login_required
from backoffice_engine.models import AdminUser, AdminProfile, User, UserProfile, File, ChatSession, ChatMessage

def admin_dashboard_view(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect("admin_login")

    # Enforce profile completion
    if hasattr(request.user, 'admin_profile') and not request.user.admin_profile.is_profile_complete:
        return redirect('admin_profile')

    section = request.GET.get('section', 'admins')
    edit_id = request.GET.get('edit_id')
    context = {'section': section, 'edit_id': edit_id}

    model_mapping = {
        'admins': AdminUser,
        'admin_profiles': AdminProfile,
        'contributors': User,
        'profiles': UserProfile,
        'files': File,
        'sessions': ChatSession,
        'messages': ChatMessage
    }
    
    ModelClass = model_mapping.get(section, AdminUser)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'delete_bulk':
            record_ids = request.POST.getlist('record_ids')
            ModelClass.objects.filter(pk__in=record_ids).delete()
            return redirect(f'/admin-dashboard/?section={section}')
            
        elif action == 'edit_save' and edit_id:
            # Simple attribute setting based on POST data excluding csrf
            record = ModelClass.objects.get(pk=edit_id)
            for key, val in request.POST.items():
                if key not in ['csrfmiddlewaretoken', 'action', 'password']:
                    if hasattr(record, key):
                        setattr(record, key, val)
            record.save()
            return redirect(f'/admin-dashboard/?section={section}')

    if edit_id:
        context['edit_record'] = ModelClass.objects.filter(pk=edit_id).first()
    else:
        if section == 'admins':
            context['records'] = AdminUser.objects.all().order_by('-date_joined')
        elif section == 'admin_profiles':
            context['records'] = AdminProfile.objects.all()
        elif section == 'contributors':
            context['records'] = User.objects.all().order_by('-created_at')
        elif section == 'profiles':
            context['records'] = UserProfile.objects.all()
        elif section == 'files':
            context['records'] = File.objects.all().order_by('-created_at')
        elif section == 'sessions':
            context['records'] = ChatSession.objects.all().order_by('-created_at')
        elif section == 'messages':
            context['records'] = ChatMessage.objects.all().order_by('-created_at')

    from backoffice_engine.choices import AdminTeamChoices, ContributorTeamChoices, SessionType, FileProcessingStatus
    context['choices'] = {
        'AdminTeamChoices': AdminTeamChoices.choices,
        'ContributorTeamChoices': ContributorTeamChoices.choices,
        'SessionType': SessionType.choices,
        'FileProcessingStatus': FileProcessingStatus.choices
    }

    return render(request, "admin/admin_dashboard.html", context)


# =========================
# ADMIN PROFILE
# =========================
def admin_profile_view(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect("admin_login")

    error = None
    profile = getattr(request.user, 'admin_profile', None)

    if not profile:
        error = "Admin profile not found."
        return render(request, "admin/admin_profile_complete.html", {"error": error})

    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        surname = request.POST.get("surname", "").strip()
        username = request.POST.get("username", "").strip()
        position = request.POST.get("position", "").strip()
        team = request.POST.get("team", "").strip()  # Should be Core or HR

        if not all([first_name, surname, username, position, team]):
            error = "All fields are required."
        else:
            try:
                profile.first_name = first_name
                profile.surname = surname
                profile.username = username
                profile.position_at_technostacks = position
                profile.team = team
                profile.is_profile_complete = True
                profile.save()

                request.user.profile_completed = True
                request.user.save()

                return redirect("admin_dashboard")
            except Exception as e:
                error = str(e)

    return render(request, "admin/admin_profile_complete.html", {
        "profile": profile,
        "error": error
    })


# =========================
# NEW CONTRIBUTOR 
# =========================
def admin_new_contributor_view(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect("admin_login")

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        position = request.POST.get("position", "").strip()
        team = request.POST.get("team", "").strip()

        try:
            from backoffice_engine.models import User, UserProfile
            from backoffice_engine.admin_auth import _check_email_domain, _check_password_strength
            
            _check_email_domain(email)
            _check_password_strength(password)
            
            if User.objects.filter(email=email).exists():
                raise Exception("Email already exists in Contributors table.")
                
            new_user = User(email=email, password=password)
            new_user.save()
            
            UserProfile.objects.create(
                user=new_user,
                position_at_technostacks=position,
                team=team,
                first_name="",
                surname="",
                username=None,
                is_profile_complete=False
            )
            from django.contrib import messages
            messages.success(request, f"Contributor {email} created successfully.")
            
        except Exception as e:
            from django.contrib import messages
            msg = getattr(e, 'message', str(e))
            messages.error(request, f"Error creating contributor: {msg}")

    return redirect("/admin-dashboard/?section=contributors")


# =========================
# ADMIN LOGOUT
# =========================
from django.contrib.auth import logout

def admin_logout_view(request):
    logout(request)
    request.session.flush()
    return redirect("admin_login")