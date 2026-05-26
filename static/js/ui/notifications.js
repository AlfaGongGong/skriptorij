

export function showToast(msg, type = 'info') {
    const c = document.getElementById('toast-container');
    if (!c) return alert(msg);
    const t = document.createElement('div');
    t.className = `toast toast-${type}`;
    t.textContent = msg;
    c.appendChild(t);
    setTimeout(() => t.classList.add('toast-visible'), 10);
    setTimeout(() => { t.classList.remove('toast-visible'); setTimeout(() => t.remove(), 300); }, 4000);
}


