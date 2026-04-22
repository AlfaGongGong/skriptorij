#!/bin/bash
echo "🧹 ČIŠĆENJE PROJEKTA SKRIPTORIJ"
cd ~/storage/shared/termux/Skriptorij || { echo "❌ Direktorij ne postoji"; exit 1; }

# Lista fajlova i foldera za brisanje
TO_DELETE=(
    # Backup fajlovi
    "*.backup"
    "*.bak"
    "*.old"
    
    # Privremeni fajlovi
    "*.tmp"
    "*.temp"
    "*_patch.txt"
    "http_patch.txt"
    "css_patch.txt"
    
    # Dupli fajlovi
    "data/packager.py"
    
    # Skripte za patch/fix (jednokratne)
    "auto_patch.sh"
    "final_ui_patch.sh"
    "fix_all.sh"
    "fix_frontend.sh"
    "split_skript.py"
    
    # Test/Debug fajlovi
    "ds.py"
    "ds_api.txt"
    "entry.py"
    "struktura.py"
    "struktura_projekta.txt"
    
    # Dupli folderi (prazni ili nepotrebni)
    "epub/__pycache__"
    "network/__pycache__"
    "processing/__pycache__"
    "core/__pycache__"
    "analysis/__pycache__"
    "utils/__pycache__"
)

# Briši fajlove po patternima
for pattern in "${TO_DELETE[@]}"; do
    echo "🔍 Tražim: $pattern"
    find . -name "$pattern" -type f -delete 2>/dev/null
    find . -name "$pattern" -type d -exec rm -rf {} + 2>/dev/null
done

# Dodatno: obriši prazne __pycache__ foldere
find . -type d -name "__pycache__" -empty -delete 2>/dev/null

# Obriši nepotrebne foldere ako su prazni
for dir in core analysis; do
    if [ -d "$dir" ] && [ -z "$(ls -A $dir 2>/dev/null)" ]; then
        rm -rf "$dir"
        echo "🗑️ Obrisan prazan folder: $dir"
    fi
done

# Obriši backup folder ako je prazan
if [ -d "backups" ] && [ -z "$(ls -A backups 2>/dev/null)" ]; then
    rm -rf backups
    echo "🗑️ Obrisan prazan folder: backups"
fi

# Ukloni nepotrebne importe iz glavnih fajlova
echo "🔧 Čišćenje importa..."

# Ukloni main.js ako postoji (koristimo app.js)
rm -f static/js/main.js

# Osiguraj da app.js nije modul u index.html
sed -i 's/type="module" //' templates/index.html 2>/dev/null

echo "✅ Čišćenje završeno!"
echo ""
echo "📊 Preostali fajlovi u projektu:"
find . -type f -name "*.py" -o -name "*.js" -o -name "*.html" -o -name "*.css" | wc -l
echo "📁 Preostali folderi:"
find . -type d | wc -l
