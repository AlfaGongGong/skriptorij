/**
 * notifications.js — Toast notifikacije
 */

/**
 * Prikaži toast notifikaciju.
 * @param {string} message
 * @param {'info'|'success'|'warning'|'error'} type
 */
export function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            toast.classList.add('toast-visible');
        });
    });

    setTimeout(() => {
        toast.classList.remove('toast-visible');
        toast.addEventListener('transitionend', () => toast.remove(), { once: true });
    }, 4000);
}

// Exponiraj na window za backwards compat
window.showToast = showToast;
