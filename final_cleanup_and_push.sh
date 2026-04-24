#!/bin/bash
echo "🧹 FINALNO ČIŠĆENJE I GITHUB PUSH"
cd ~/storage/shared/termux/Skriptorij || exit 1

# 1. Obriši sve nepotrebne fajlove
echo "🗑️ Brisanje nepotrebnih fajlova..."

# Cleanup i patch skripte
rm -f add_final_features.sh final_fix.sh fix_fleet_complete.sh fix_live_preview.sh 2>/dev/null
rm -f fix_pipeline_steps.sh fix_refresh_final.sh fix_ui_refresh.sh 2>/dev/null
rm -f fix_rotation.sh fix_cerebras_sambanova.sh fix_cerebras_sambanova_v2.sh 2>/dev/null
rm -f fix_models_final.sh fix_all_models.sh fix_frontend.sh 2>/dev/null
rm -f complete_fix.sh disable_broken_providers.sh dynamic_models_fix.sh 2>/dev/null
rm -f emergency_fix.sh emergency_provider_fix.sh working_models.sh 2>/dev/null
rm -f cleanup_project.sh booklyfi_fix_all.sh generate_project_summary.sh 2>/dev/null

# Dupli fajlovi
rm -f static/js/app-all.js static/js/app.js.bak static/js/app.js.bak_state 2>/dev/null
rm -f api_fleet.py.dynamic_backup dynamic_resolve_models.py 2>/dev/null
rm -f skriptorij.py.backup skriptorij.py.groq_fix skriptorij.py.dynamic_backup 2>/dev/null
rm -f templates/index.html.bak static/css/style.css.bak 2>/dev/null
rm -f app.py.broken app_patch.py 2>/dev/null
rm -f str.py struktura_projekta.txt js.txt 2>/dev/null

# Backup folderi
rm -rf backups_20260423_092047 2>/dev/null
rm -rf backups 2>/dev/null

# __pycache__ i .pyc
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null

# node_modules (ako nije potreban)
# rm -rf node_modules 2>/dev/null

echo "✅ Nepotrebni fajlovi obrisani"

# 2. Ažuriraj PROJECT_SUMMARY.txt
cat > PROJECT_SUMMARY.txt << 'SUMMARY'
================================================================================
BOOKLYFI TURBO CHARGED
AI-Powered Book Translation & Refinement Engine
================================================================================

SAŽETAK
--------------------------------------------------------------------------------
BOOKLYFI je napredni sistem za automatsko prevođenje i lekturu EPUB/MOBI knjiga
sa engleskog na bosanski/hrvatski jezik. Koristi flotu od 50+ besplatnih API
ključeva preko više AI provajdera sa automatskim failover-om i pametnim
rutiranjem modela.

FUNKCIONALNOSTI
--------------------------------------------------------------------------------
- Upload i odabir knjiga (EPUB/MOBI)
- Više AI provajdera sa automatskim prebacivanjem
- Live dashboard sa progresom, ETA, pipeline koracima
- Fleet manager sa health barovima, toggle dugmadima za ključeve
- Checkpoint sistem - nastavlja obradu od mesta prekida
- Neon animacije na BOOKLYFI naslovu
- Potpuno responzivan - radi na desktopu i Androidu
- Automatska rotacija modela za Google API (Gemma → Gemini Flash Lite)

ARHITEKTURA
--------------------------------------------------------------------------------
Frontend: HTML5 + CSS3 + vanilla JavaScript (app-clean.js)
Backend: Flask + Python 3.13
Engine: Modularni pipeline (core/, network/, processing/, epub/, utils/)
AI Provideri: Gemini, Groq, Mistral, Sambanova, OpenRouter, Cohere, Chutes,
              HuggingFace, Kluster, Together

INSTALACIJA I POKRETANJE
--------------------------------------------------------------------------------
1. pip install -r requirements.txt
2. Konfigurisati API ključeve u dev_api.json
3. python main.py
4. Otvoriti http://127.0.0.1:8080

GLAVNI FAJLOVI
--------------------------------------------------------------------------------
main.py              - Ulazna tačka servera
app.py               - Flask aplikacija sa svim /api/* rutama
api_fleet.py         - Fleet Manager (API ključevi, health, limiti)
run.py               - Wrapper za modularni engine
core/engine.py       - Klasa SkriptorijAllInOne
core/prompts.py      - AI promptovi za sve uloge
network/http_client.py - HTTP zahtevi sa retry logikom
network/provider_router.py - Odabir provajdera po ulozi
processing/pipeline.py - Glavni pipeline obrade
templates/index.html - Frontend HTML
static/css/style.css - Kompletan CSS (dark theme, neon akcenti)
static/js/app-clean.js - Sva JavaScript logika

STATUS (April 2026)
--------------------------------------------------------------------------------
✅ Upload i odabir knjiga
✅ Pokretanje i praćenje obrade
✅ Dashboard sa ETA, pipeline koracima, live preview
✅ Fleet panel sa health barovima i toggle dugmadima
✅ API ključevi (dodavanje, brisanje)
✅ Dnevnik (audit log) sa automatskim skrolom
✅ Spremanje stanja na refresh
✅ Neon animacije
✅ Google model rotacija (Gemma 3 27B → Gemini Flash Lite)
✅ Checkpoint sistem za nastavak obrade

================================================================================
SUMMARY

# 3. Ažuriraj FILE_TREE.txt
find . -not -path '*/\.*' -not -path '*/node_modules/*' -not -path '*/__pycache__/*' -not -path '*/data/_skr_*/*' -not -path '*.pyc' | sort > FILE_TREE.txt

echo "✅ PROJECT_SUMMARY.txt i FILE_TREE.txt ažurirani"

# 4. Git push
if git rev-parse --git-dir > /dev/null 2>&1; then
    git add -A
    git commit -m "🚀 BOOKLYFI V10.2 Final - Stabilna produkcijska verzija
    
    - Modularni engine (core, network, processing, epub, utils)
    - Fleet manager sa automatskim deaktiviranjem ključeva
    - Google model rotacija (Gemma 3 27B → Gemini Flash Lite)
    - Kompletan frontend sa dashboardom, ETA, pipeline koracima
    - Spremanje stanja na refresh
    - Checkpoint sistem za resume obrade
    - Očišćen projekat od nepotrebnih fajlova"
    
    git push origin main 2>/dev/null && echo "✅ Push uspješan!" || echo "⚠️ Push nije uspio - provjeri git konfiguraciju"
else
    echo "⚠️ Git nije inicijaliziran. Pokrećem git init..."
    git init
    git add -A
    git commit -m "🚀 BOOKLYFI V10.2 - Inicijalni commit"
    echo "✅ Git inicijaliziran. Dodaj remote sa:"
    echo "   git remote add origin https://github.com/TvojUsername/Skriptorij.git"
    echo "   git push -u origin main"
fi

echo ""
echo "🎉 SVE GOTOVO!"
echo "   Projekat očišćen i spreman za produkciju"
echo "   Dokumentacija ažurirana"
