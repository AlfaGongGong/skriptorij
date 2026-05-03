#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# booklyfi_restart.sh
# Restartuje server, briše keš, pokreće ispočetka
# ============================================================

set -e

echo "📦 BOOKLYFI - Restart servera"
echo "=============================="
echo ""

# ----------------------------------------------------------
# 1. Zaustavi Flask server
# ----------------------------------------------------------
echo "🛑 Zaustavljam Flask server..."

# Nađi PID Flask procesa
FLASK_PID=$(ps aux | grep "[p]ython.*main.py" | awk '{print $2}')

if [ -n "$FLASK_PID" ]; then
    echo "   Pronađen Flask PID: $FLASK_PID"
    kill "$FLASK_PID" 2>/dev/null
    sleep 2
    
    # Ako je još živ, ubij ga silom
    if kill -0 "$FLASK_PID" 2>/dev/null; then
        echo "   ⚠️ Proces se nije zaustavio, prisilno gašenje..."
        kill -9 "$FLASK_PID" 2>/dev/null
        sleep 1
    fi
    echo "   ✅ Flask server zaustavljen"
else
    echo "   ℹ️ Flask server nije pronađen (možda nije ni pokrenut)"
fi

# Takođe ubij sve Python procese koji koriste port 8080
PORT_PID=$(lsof -ti:8080 2>/dev/null || true)
if [ -n "$PORT_PID" ]; then
    echo "   🧹 Čistim port 8080 (PID: $PORT_PID)..."
    kill -9 $PORT_PID 2>/dev/null || true
    sleep 1
    echo "   ✅ Port 8080 oslobođen"
fi

echo ""

# ----------------------------------------------------------
# 2. Obriši keš
# ----------------------------------------------------------
echo "🧹 Brišem keš..."

# Python __pycache__
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Flask sesije (ako postoje)
rm -rf flask_session/ 2>/dev/null || true

# Privremeni fajlovi
rm -rf tmp/ .cache/ 2>/dev/null || true

echo "   ✅ Keš obrisan"
echo ""

# ----------------------------------------------------------
# 3. Proveri da li fajlovi postoje
# ----------------------------------------------------------
echo "🔍 Proveravam fajlove..."

if [ ! -f "main.py" ]; then
    echo "❌ main.py ne postoji – nisi u root folderu"
    exit 1
fi

if [ ! -f "templates/index.html" ]; then
    echo "❌ templates/index.html ne postoji"
    exit 1
fi

if [ ! -f "static/js/main.js" ]; then
    echo "❌ static/js/main.js ne postoji"
    exit 1
fi

if [ ! -f "static/css/style.css" ]; then
    echo "⚠️ static/css/style.css ne postoji (nastavljam bez njega)"
fi

echo "   ✅ Svi potrebni fajlovi postoje"
echo ""

# ----------------------------------------------------------
# 4. Proveri Python i pip
# ----------------------------------------------------------
echo "🐍 Proveravam Python..."

PYTHON_VERSION=$(python3 --version 2>&1 || echo "nepoznato")
echo "   $PYTHON_VERSION"

# Proveri da li su svi paketi instalirani
echo "   Proveravam zavisnosti..."
MISSING=""

python3 -c "import flask" 2>/dev/null || MISSING="$MISSING flask"
python3 -c "import bs4" 2>/dev/null || MISSING="$MISSING beautifulsoup4"
python3 -c "import httpx" 2>/dev/null || MISSING="$MISSING httpx"
python3 -c "import lxml" 2>/dev/null || MISSING="$MISSING lxml"
python3 -c "import dotenv" 2>/dev/null || MISSING="$MISSING python-dotenv"

if [ -n "$MISSING" ]; then
    echo "   ⚠️ Nedostaju paketi:$MISSING"
    echo "   📦 Instaliram..."
    pip install flask beautifulsoup4 httpx lxml python-dotenv requests
    echo "   ✅ Paketi instalirani"
else
    echo "   ✅ Svi paketi su instalirani"
fi

echo ""

# ----------------------------------------------------------
# 5. Proveri dev_api.json
# ----------------------------------------------------------
echo "🔑 Proveravam API ključeve..."

if [ -f "dev_api.json" ]; then
    KEY_COUNT=$(python3 -c "
import json
with open('dev_api.json') as f:
    keys = json.load(f)
total = sum(len(v) for v in keys.values())
print(total)
" 2>/dev/null || echo "0")
    
    if [ "$KEY_COUNT" -gt 0 ]; then
        echo "   ✅ dev_api.json postoji ($KEY_COUNT ključeva)"
    else
        echo "   ⚠️ dev_api.json postoji ali nema ključeva"
    fi
else
    echo "   ⚠️ dev_api.json ne postoji – kreiraj ga sa API ključevima"
fi

echo ""

# ----------------------------------------------------------
# 6. Pokreni server
# ----------------------------------------------------------
echo "🚀 Pokrećem server..."
echo ""

python3 main.py &
FLASK_NEW_PID=$!

# Sačekaj da server startuje
sleep 3

# Proveri da li je startovao
if kill -0 "$FLASK_NEW_PID" 2>/dev/null; then
    echo ""
    echo "===================================="
    echo "✅ Server pokrenut!"
    echo ""
    echo "   PID: $FLASK_NEW_PID"
    echo "   URL: http://localhost:8080"
    echo ""
    echo "📱 Otvori browser i idi na http://localhost:8080"
    echo ""
    echo "💡 Saveti:"
    echo "   - Hard Refresh: Ctrl+Shift+R (ili povuci ekran dole 3x)"
    echo "   - Ako ne radi, obriši keš browsera (Settings → Clear browsing data)"
    echo "   - Za zaustavljanje: kill $FLASK_NEW_PID"
    echo ""
    echo "📋 Procesi na portu 8080:"
    lsof -i:8080 2>/dev/null | grep LISTEN || echo "   (nema aktivnih)"
    echo ""
    echo "📂 Log fajlovi su u folderu logs/ (ako postoji)"
    echo "===================================="
else
    echo ""
    echo "❌ Server nije uspeo da se pokrene!"
    echo "   Proveri greške:"
    echo "   tail -f nohup.out (ako postoji)"
    echo "   ili pokreni python3 main.py ručno da vidiš greške"
    echo "   Prikaži PID lsof -ti:8080"
    echo "   Zaustavi pkill -f 'python main.py" 2>/dev/null'
    exit 1
fi