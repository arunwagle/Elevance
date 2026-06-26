/**
 * Session inactivity timer — auto-logout after 60s of inactivity.
 * Shows warning modal at 45s, redirects at 60s.
 */
(function() {
    const TIMEOUT_SECONDS = 60;
    const WARNING_AT = 45;
    let lastActivity = Date.now();
    let warningShown = false;

    const modal = document.getElementById('timeout-modal');
    const countdown = document.getElementById('timeout-countdown');
    const stayBtn = document.getElementById('stay-logged-in');

    function resetTimer() {
        lastActivity = Date.now();
        warningShown = false;
        if (modal) modal.classList.add('hidden');
    }

    // Track user activity
    ['mousemove', 'keypress', 'click', 'scroll'].forEach(event => {
        document.addEventListener(event, function() {
            if (!warningShown) lastActivity = Date.now();
        }, { passive: true });
    });

    // Stay Logged In button
    if (stayBtn) {
        stayBtn.addEventListener('click', function() {
            fetch('/auth/heartbeat', { method: 'POST' })
                .then(() => resetTimer())
                .catch(() => window.location.href = '/login');
        });
    }

    // Check every second
    setInterval(function() {
        const elapsed = (Date.now() - lastActivity) / 1000;
        const remaining = Math.max(0, Math.ceil(TIMEOUT_SECONDS - elapsed));

        if (elapsed >= TIMEOUT_SECONDS) {
            window.location.href = '/logout';
        } else if (elapsed >= WARNING_AT && !warningShown) {
            warningShown = true;
            if (modal) modal.classList.remove('hidden');
        }

        if (countdown && warningShown) {
            countdown.textContent = remaining;
        }
    }, 1000);
})();
