// ============================================================================
// SKRIPTORIJ V10.2 — KOMPLETNI APP.JS (SA SPREMANJEM STANJA I NEON ANIMACIJOM)
// ============================================================================
console.log('✅ BOOKLYFI app.js učitan');

// ---------- GLOBALNE ----------
let pollInterval = null;
let _activeTab = 'status';

// ---------- TEMA ----------
function toggleTheme() {
    document.body.classList.toggle('light-theme');
    localStorage.setItem('skriptorij-theme', document.body.classList.contains('light-theme') ? 'light' : 'dark');
    saveAppState();
}
function applyStoredTheme() {
    if (localStorage.getItem('skriptorij-theme') === 'light') document.body.classList.add('light-theme');
}

// ---------- SPREMANJE STANJA ----------
function saveAppState() {
    const state = {
        selectedBook: document.getElementById('book-select')?.value || '',
        selectedModel: document.getElementById('model-select')?.value || 'V8_TURBO',
        selectedMode: document.getElementById('mode-select')?.value || 'PREVOD',
        currentWizardStep: document.getElementById('wizard-page-2')?.classList.contains('hidden') ? 1 : 2,
        dashboardVisible: !document.getElementById('dashboard-screen')?.classList.contains('hidden'),
        currentTab: _activeTab || 'status',
        theme: document.body.classList.contains('light-theme') ? 'light' : 'dark'
    };
    localStorage.setItem('skriptorij_app_state', JSON.stringify(state));
}
function restoreAppState() {
    const saved = localStorage.getItem('skriptorij_app_state');
    if (!saved) return false;
    try {
        const state = JSON.parse(saved);
        setTimeout(() => {
            const bookSelect = document.getElementById('book-select');
            if (bookSelect && state.selectedBook && Array.from(bookSelect.options).some(o => o.value === state.selectedBook)) {
                bookSelect.value = state.selectedBook;
            }
        }, 500);
        setTimeout(() => {
            const ms = document.getElementById('model-select'); if (ms && state.selectedModel) ms.value = state.selectedModel;
            const md = document.getElementById('mode-select'); if (md && state.selectedMode) md.value = state.selectedMode;
        }, 300);
        if (state.currentWizardStep === 2) {
            setTimeout(() => {
                document.getElementById('wizard-page-1')?.classList.add('hidden');
                document.getElementById('wizard-page-2')?.classList.remove('hidden');
                document.getElementById('ws-indicator-1')?.classList.replace('active', 'completed');
                document.getElementById('ws-indicator-2')?.classList.add('active');
            }, 100);
        }
        if (state.dashboardVisible) {
            setTimeout(() => {
                document.getElementById('setup-screen')?.classList.add('hidden');
                document.getElementById('dashboard-screen')?.classList.remove('hidden');
                if (pollInterval) clearInterval(pollInterval);
                pollInterval = setInterval(updateDashboard, 2000);
                updateDashboard();
            }, 200);
        }
        if (state.currentTab) setTimeout(() => switchTab(state.currentTab), 150);
        return true;
    } catch (e) { return false; }
}

// ---------- TABOVI ----------
function switchTab(tab) {
    _activeTab = tab;
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('tab-panel-active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('tab-active'));
    document.getElementById('tab-' + tab)?.classList.add('tab-panel-active');
    document.getElementById('tbtn-' + tab)?.classList.add('tab-active');
    if (tab === 'fleet') updateFleetPool();
    if (tab === 'keys') loadApiKeys();
    if (tab === 'log') { const a = document.getElementById('audit'); if(a) a.scrollTop = a.scrollHeight; }
    saveAppState();
}

// ---------- SETUP ----------
function toggleSetup() {
    const s = document.getElementById('setup-screen'), d = document.getElementById('dashboard-screen');
    if (!s) return;
    if (s.classList.contains('hidden')) { s.classList.remove('hidden'); d?.classList.add('hidden'); }
    else { s.classList.add('hidden'); d?.classList.remove('hidden'); }
    saveAppState();
}
function nextSetupStep() {
    if (!document.getElementById('book-select')?.value) { alert('⚠️ Odaberi knjigu!'); return; }
    document.getElementById('wizard-page-1')?.classList.add('hidden');
    document.getElementById('wizard-page-2')?.classList.remove('hidden');
    document.getElementById('ws-indicator-1')?.classList.replace('active', 'completed');
    document.getElementById('ws-indicator-2')?.classList.add('active');
    saveAppState();
}
function prevSetupStep() {
    document.getElementById('wizard-page-2')?.classList.add('hidden');
    document.getElementById('wizard-page-1')?.classList.remove('hidden');
    document.getElementById('ws-indicator-2')?.classList.remove('active');
    document.getElementById('ws-indicator-1')?.classList.replace('completed', 'active');
    saveAppState();
}

// ---------- KNJIGE ----------
function loadBooks() {
    fetch('/api/books').then(r=>r.json()).then(d=>{
        const s=document.getElementById('book-select'); if(!s)return;
        s.innerHTML='<option value="">-- Odaberi knjigu --</option>';
        (d.books||[]).forEach(b=>s.add(new Option(b.name,b.path)));
        if(d.last_book) s.value=d.last_book;
        setTimeout(saveAppState, 500);
    }).catch(e=>console.error(e));
}
function loadModels() {
    fetch('/api/dev_models').then(r=>r.json()).then(m=>{
        const s=document.getElementById('model-select'); if(!s)return;
        s.innerHTML=''; (m||[]).forEach(x=>s.add(new Option(x==='V8_TURBO'?'⚡ V8 TURBO':x,x)));
        s.value='V8_TURBO';
    });
}
function _initUploadListener() {
    const i=document.getElementById('book-file');
    i?.addEventListener('change', e=>{
        const f=e.target.files[0]; if(!f)return;
        const fd=new FormData(); fd.append('file',f);
        fetch('/api/upload_book',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
            if(d.error) throw new Error(d.error); loadBooks(); alert('✅ Uploadovano: '+d.name);
        }).catch(e=>alert('❌ '+e.message));
        i.value='';
    });
}

// ---------- ENGINE ----------
function startEngine() {
    const book=document.getElementById('book-select')?.value, model=document.getElementById('model-select')?.value||'V8_TURBO', mode=document.getElementById('mode-select')?.value||'PREVOD';
    if(!book){alert('⚠️ Odaberi knjigu!');return;}
    const btn=document.getElementById('btn-start'); if(btn){btn.innerText='⏳ Inicijalizacija...';btn.disabled=true;}
    fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({book,model,mode})})
        .then(r=>r.json()).then(d=>{if(d.error)throw new Error(d.error); switchToDashboard();})
        .catch(e=>{alert('❌ '+e.message); if(btn){btn.innerText='🚀 Pokreni Sistem';btn.disabled=false;}});
}
function switchToDashboard() {
    document.getElementById('setup-screen')?.classList.add('hidden');
    document.getElementById('dashboard-screen')?.classList.remove('hidden');
    if(pollInterval)clearInterval(pollInterval);
    pollInterval=setInterval(updateDashboard,2000);
    updateDashboard();
    saveAppState();
}
function updateDashboard() {
    fetch('/api/status').then(r=>r.json()).then(d=>{
        document.getElementById('ph').textContent=d.status||'IDLE';
        document.getElementById('ae').textContent=d.active_engine||'---';
        document.getElementById('bi').textContent=d.current_file||'---';
        document.getElementById('ok').textContent=d.ok||'0/0';
        document.getElementById('pct').textContent=(d.pct||0)+'%';
        document.getElementById('fill').style.width=(d.pct||0)+'%';
        const dot=document.getElementById('status-dot'), s=(d.status||'').toUpperCase();
        if(dot) dot.className='dot '+(s.includes('TOKU')?'dot-active':s==='PAUZIRANO'?'dot-paused':'dot-idle');
        const audit=document.getElementById('audit'); if(audit&&d.live_audit){ audit.innerHTML=d.live_audit; audit.scrollTop=audit.scrollHeight; }
    });
}
function sendCommand(cmd){ fetch('/control/'+cmd,{method:'POST'}).catch(e=>console.error); }

// ---------- FLEET ----------
function updateFleetPool() {
    fetch('/api/fleet').then(r=>r.json()).then(data=>{
        const c=document.getElementById('fleet-cards-container'); if(!c)return;
        let h='';
        for(const [p,info] of Object.entries(data)){
            const active=info.active||0, total=info.total||0, keys=info.keys||[];
            const icon=active>0?'🟢':(total-active>0?'🟡':'🔴');
            h+=`<details class="fleet-card"><summary class="fleet-card-header"><span class="fleet-card-icon">${icon}</span><span class="fleet-card-name">${p}</span><span class="fleet-card-count">${active}/${total}</span><span class="fleet-chevron">▼</span></summary><div class="fleet-keys-grid">`;
            keys.forEach(k=>{
                const status=k.available?'aktivan':(k.cooldown_remaining>0?'limitiran':'blokiran');
                h+=`<div class="fleet-key-pill fleet-key-${status}"><span>${k.masked}</span><span>${k.available?'✅':(k.cooldown_remaining>0?'⏳':'🔴')}</span></div>`;
            });
            h+='</div></details>';
        }
        c.innerHTML=h||'<p style="padding:20px;text-align:center;">Nema provajdera</p>';
        const badge=document.getElementById('fleet-total-count'); if(badge) badge.textContent=Object.values(data).reduce((s,i)=>s+(i.active||0),0);
    });
}

// ---------- API KLJUČEVI ----------
function loadApiKeys(){ fetch('/api/keys').then(r=>r.json()).then(d=>{ const c=document.getElementById('keys-list'); if(!c)return; let h='<table class="fleet-table">'; Object.entries(d).forEach(([p,keys])=>keys.forEach(k=>h+=`<tr><td>${p}</td><td>${k}</td><td><button class="btn btn-danger btn-sm" onclick="deleteApiKey('${p}','${k}')">🗑</button></td></tr>`)); c.innerHTML=h+'</table>'; }); }
function addApiKey(){ const p=document.getElementById('key-provider-select')?.value, k=document.getElementById('key-input')?.value.trim(); if(!p||!k){alert('⚠️ Popuni polja');return;} fetch('/api/keys/'+p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:k})}).then(r=>r.json()).then(d=>{if(d.error)throw new Error(d.error); alert('✅ Dodano'); document.getElementById('key-input').value=''; loadApiKeys(); }).catch(e=>alert('❌ '+e.message)); }
function deleteApiKey(p,k){ if(!confirm('Obrisati?'))return; fetch('/api/keys/'+p+'/'+k,{method:'DELETE'}).then(()=>loadApiKeys()); }

// ---------- NEON ANIMACIJA ----------
(function() {
    const NEON = ["#60a5fa", "#a78bfa", "#4ade80", "#fbbf24", "#f87171", "#06b6d4"];
    let letters = null, timer = null;
    function flash() {
        if (!letters?.length) { letters = document.querySelectorAll("#app-logo-title .neon-letter"); if (!letters.length) return; }
        const count = Math.random() < 0.4 ? 2 : 1;
        for (let k = 0; k < count; k++) {
            const idx = Math.floor(Math.random() * letters.length);
            const color = NEON[Math.floor(Math.random() * NEON.length)];
            const shadow = `0 0 6px ${color}, 0 0 18px ${color}, 0 0 36px ${color}`;
            const el = letters[idx];
            el.style.setProperty("-webkit-text-fill-color", color);
            el.style.textShadow = shadow;
            setTimeout(() => { el.style.removeProperty("-webkit-text-fill-color"); el.style.textShadow = ""; }, 180 + Math.random() * 320);
        }
        timer = setTimeout(flash, 120 + Math.random() * 480);
    }
    document.addEventListener("DOMContentLoaded", () => { letters = document.querySelectorAll("#app-logo-title .neon-letter"); if (letters.length) setTimeout(flash, 600); });
    window.addEventListener("beforeunload", () => { if (timer) clearTimeout(timer); });
})();

// ---------- EKSPORTI I INIT ----------
window.toggleTheme=toggleTheme; window.switchTab=switchTab; window.toggleSetup=toggleSetup;
window.nextSetupStep=nextSetupStep; window.prevSetupStep=prevSetupStep; window.startEngine=startEngine;
window.sendCommand=sendCommand; window.addApiKey=addApiKey; window.deleteApiKey=deleteApiKey;

document.addEventListener('DOMContentLoaded', ()=>{
    applyStoredTheme();
    const restored = restoreAppState();
    loadBooks(); loadModels(); _initUploadListener();
    if (!restored) switchTab('status');
    updateFleetPool();
    setInterval(()=>{ if(_activeTab==='fleet') updateFleetPool(); }, 10000);
    setInterval(()=>{ if(!document.getElementById('setup-screen')?.classList.contains('hidden')) updateDashboard(); }, 3000);
    window.addEventListener('beforeunload', saveAppState);
    setInterval(saveAppState, 10000);
});
