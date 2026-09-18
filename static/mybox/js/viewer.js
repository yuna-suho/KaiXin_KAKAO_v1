(function () {
    var PC_MIN_WIDTH = 1024;
    var toastTimer = null;

    function isMobileUa() {
        var ua = navigator.userAgent || '';
        return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile/i.test(ua)
            || (navigator.maxTouchPoints > 1 && /Macintosh/i.test(ua));
    }

    function syncLayoutClass() {
        var html = document.documentElement;
        var ua = navigator.userAgent || '';
        var mobile = isMobileUa() || window.innerWidth < PC_MIN_WIDTH;
        if (mobile) {
            html.className = /iPhone|iPad|iPod/i.test(ua) ? 'ios' : 'aos';
            return;
        }
        html.className = /Mac OS X|Macintosh/i.test(ua) ? 'pc mac' : 'pc win';
    }

    function showToast(message) {
        var toast = document.getElementById('toast');
        if (!toast) {
            return;
        }
        toast.textContent = message;
        toast.hidden = false;
        if (toastTimer) {
            window.clearTimeout(toastTimer);
        }
        toastTimer = window.setTimeout(function () {
            toast.hidden = true;
        }, 1800);
    }

    syncLayoutClass();
    window.addEventListener('resize', syncLayoutClass);

    var closeButton = document.getElementById('button_viewer_close');
    if (closeButton && document.body && document.body.getAttribute('data-embed') !== '1') {
        closeButton.addEventListener('click', function () {
            var fallbackUrl = (closeButton.getAttribute('data-fallback-url') || '').trim();
            window.close();
            if (window.top && window.top !== window) {
                try {
                    window.top.close();
                } catch (e) {}
            }
            if (!fallbackUrl) {
                return;
            }
            window.setTimeout(function () {
                window.location.replace(fallbackUrl);
            }, 150);
        });
    }

    var saveButton = document.getElementById('button_mybox_save');
    if (saveButton) {
        saveButton.addEventListener('click', function () {
            showToast('MYBOX에 저장되었습니다.');
        });
    }
})();
