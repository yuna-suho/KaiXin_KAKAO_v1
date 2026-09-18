from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from kaixin.store import find_admin_by_id

SESSION_ADMIN_ID = 'kaixin_admin_id'
PENDING_MESSAGE = 'Your account is pending superadmin approval.'


def get_current_admin(request):
    admin_id = request.session.get(SESSION_ADMIN_ID)
    if not admin_id:
        return None
    return find_admin_by_id(admin_id)


def login_admin(request, admin):
    request.session[SESSION_ADMIN_ID] = str(admin['_id'])
    request.session.cycle_key()


def logout_admin(request):
    request.session.pop(SESSION_ADMIN_ID, None)
    request.session.cycle_key()


def login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        admin = get_current_admin(request)
        if admin is None:
            return redirect('kaixin:login')
        if not admin.get('is_approved'):
            logout_admin(request)
            messages.info(request, PENDING_MESSAGE)
            return redirect('kaixin:login')
        request.kaixin_admin = admin
        return view_func(request, *args, **kwargs)

    return wrapper


def superadmin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        admin = get_current_admin(request)
        if admin is None:
            return redirect('kaixin:login')
        if not admin.get('is_approved'):
            logout_admin(request)
            messages.info(request, PENDING_MESSAGE)
            return redirect('kaixin:login')
        if not admin.get('is_superadmin'):
            return redirect('kaixin:dashboard')
        request.kaixin_admin = admin
        return view_func(request, *args, **kwargs)

    return wrapper
