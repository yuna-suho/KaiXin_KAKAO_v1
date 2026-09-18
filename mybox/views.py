import re

from django.shortcuts import render
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET

from accounts.policy_store import get_blacklist_policy, get_mybox_display

_MOBILE_UA = re.compile(
    r'Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile',
    re.I,
)
_IOS_UA = re.compile(r'iPhone|iPad|iPod', re.I)
_MAC_UA = re.compile(r'Mac OS X|Macintosh', re.I)


def _html_class(request):
    ua = request.META.get('HTTP_USER_AGENT') or ''
    if _MOBILE_UA.search(ua):
        return 'ios' if _IOS_UA.search(ua) else 'aos'
    if _MAC_UA.search(ua):
        return 'pc mac'
    return 'pc win'


@require_GET
def image_viewer(request, embed=False):
    policy = get_blacklist_policy()
    display = get_mybox_display()
    return render(
        request,
        'mybox/viewer.html',
        {
            'filename': display['filename'],
            'extension': display['extension'],
            'filesize': display['filesize'],
            'image_url': display['image_url'],
            'current': 1,
            'total': 1,
            'page_title': display['page_title'],
            'html_class': _html_class(request),
            'mybox_redirect_url': policy['mybox_redirect_url'],
            'embed': embed,
        },
    )


@require_GET
@xframe_options_sameorigin
def intro_image_viewer(request):
    return image_viewer(request, embed=True)
