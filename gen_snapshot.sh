#!/usr/bin/env bash
# gen_snapshot.sh — Project Snapshot Generator
# Generira PROJECT_SNAPSHOT.md za upload Claude-u
# Korištenje: bash gen_snapshot.sh [/putanja/do/projekta]
# Bez argumenta: koristi trenutni direktorij

set -euo pipefail

PROJECT_DIR="${1:-.}"
PROJECT_DIR="$(realpath "$PROJECT_DIR")"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
# Output u Downloads — dostupan iz Acode/file managera
DOWNLOADS_DIR="${HOME}/storage/downloads"
# Fallback ako termux-setup-storage nije pokrenut
if [ ! -d "$DOWNLOADS_DIR" ]; then
  DOWNLOADS_DIR="${HOME}/downloads"
  mkdir -p "$DOWNLOADS_DIR"
fi
OUT="$DOWNLOADS_DIR/${PROJECT_NAME}_SNAPSHOT.md"
TMPFILE="$(mktemp)"

# ─────────────────────────────────────────────────────────────────────────────
# KONFIGURACIJA
# ─────────────────────────────────────────────────────────────────────────────

# Direktoriji koji se kompletno preskačuju
SKIP_DIRS=(
  ".git" ".svn" ".hg"
  "node_modules" "__pycache__" ".pytest_cache" ".mypy_cache"
  "venv" ".venv" "env" ".env" "virtualenv"
  "dist" "build" ".build" "out" "target"
  ".idea" ".vscode" ".DS_Store"
  "site-packages" "lib64"
  "*.egg-info"
)

# Ekstenzije koje se preskačuju
SKIP_EXTS=(
  # Kompajlirani
  ".pyc" ".pyo" ".pyd" ".so" ".dll" ".dylib" ".exe" ".o" ".a"
  # Binarni media
  ".png" ".jpg" ".jpeg" ".gif" ".bmp" ".ico" ".svg" ".webp"
  ".mp3" ".mp4" ".wav" ".ogg" ".flac"
  ".ttf" ".otf" ".woff" ".woff2" ".eot"
  ".pdf" ".doc" ".docx" ".xls" ".xlsx"
  ".zip" ".tar" ".gz" ".bz2" ".xz" ".7z" ".rar"
  ".epub" ".mobi" ".azw"
  # Lock fajlovi
  ".lock"
  # DB
  ".db" ".sqlite" ".sqlite3"
)

# Fajlovi koji se preskačuju po imenu (secrets, generated, noise)
SKIP_FILES=(
  ".env" ".env.local" ".env.production" ".env.staging"
  "*.key" "*.pem" "*.cert" "*.crt" "*.p12" "*.pfx"
  "dev_api.json" "api_keys.json" "secrets.json" "credentials.json"
  "*.bak" "*.bak2" "*.tmp" "*.orig"
  "package-lock.json" "yarn.lock" "poetry.lock" "Pipfile.lock"
  "*.min.js" "*.min.css" "*.map"
  "PROJECT_SNAPSHOT.md"
  ".gitignore" ".dockerignore"
  "Thumbs.db" ".DS_Store"
)

# Maksimalna veličina jednog fajla (bytes) — veći se trunckiraju
MAX_FILE_BYTES=50000

# Maksimalna ukupna veličina snapshotа (bytes) — zaustavlja se kad dostigne
MAX_TOTAL_BYTES=200000

# Ekstenzije koje su "code" (prikazuju se s bojom u markdown-u)
declare -A LANG_MAP
LANG_MAP[".py"]="python"
LANG_MAP[".js"]="javascript"
LANG_MAP[".ts"]="typescript"
LANG_MAP[".jsx"]="jsx"
LANG_MAP[".tsx"]="tsx"
LANG_MAP[".sh"]="bash"
LANG_MAP[".bash"]="bash"
LANG_MAP[".html"]="html"
LANG_MAP[".xhtml"]="html"
LANG_MAP[".css"]="css"
LANG_MAP[".json"]="json"
LANG_MAP[".yaml"]="yaml"
LANG_MAP[".yml"]="yaml"
LANG_MAP[".toml"]="toml"
LANG_MAP[".ini"]="ini"
LANG_MAP[".cfg"]="ini"
LANG_MAP[".xml"]="xml"
LANG_MAP[".sql"]="sql"
LANG_MAP[".md"]="markdown"
LANG_MAP[".txt"]="text"
LANG_MAP[".rst"]="text"
LANG_MAP[".java"]="java"
LANG_MAP[".c"]="c"
LANG_MAP[".cpp"]="cpp"
LANG_MAP[".h"]="c"
LANG_MAP[".rs"]="rust"
LANG_MAP[".go"]="go"
LANG_MAP[".rb"]="ruby"
LANG_MAP[".php"]="php"
LANG_MAP[".swift"]="swift"
LANG_MAP[".kt"]="kotlin"
LANG_MAP[".r"]="r"

# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNKCIJE
# ─────────────────────────────────────────────────────────────────────────────

should_skip_dir() {
  local dir="$1"
  local base
  base="$(basename "$dir")"
  for pattern in "${SKIP_DIRS[@]}"; do
    # Glob match
    case "$base" in
      $pattern) return 0 ;;
    esac
  done
  return 1
}

should_skip_file() {
  local file="$1"
  local base ext
  base="$(basename "$file")"
  ext="${base##*.}"
  [ "$ext" = "$base" ] && ext=""
  [ -n "$ext" ] && ext=".$ext"

  # Provjera ekstenzije
  for skip_ext in "${SKIP_EXTS[@]}"; do
    [ "$ext" = "$skip_ext" ] && return 0
  done

  # Provjera imena (glob)
  for pattern in "${SKIP_FILES[@]}"; do
    case "$base" in
      $pattern) return 0 ;;
    esac
  done

  return 1
}

get_lang() {
  local file="$1"
  local base ext
  base="$(basename "$file")"
  ext="${base##*.}"
  [ "$ext" = "$base" ] && ext=""
  [ -n "$ext" ] && ext=".$ext"
  echo "${LANG_MAP[$ext]:-text}"
}

human_size() {
  local bytes="$1"
  if [ "$bytes" -gt 1048576 ]; then
    echo "$((bytes / 1048576))MB"
  elif [ "$bytes" -gt 1024 ]; then
    echo "$((bytes / 1024))KB"
  else
    echo "${bytes}B"
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# SAKUPLJANJE FAJLOVA
# ─────────────────────────────────────────────────────────────────────────────

collect_files() {
  # find s prune za skip direktorije
  local prune_args=()
  for d in "${SKIP_DIRS[@]}"; do
    prune_args+=(-name "$d" -prune -o)
  done

  find "$PROJECT_DIR" \
    "${prune_args[@]}" \
    -type f -print 2>/dev/null | sort
}

# ─────────────────────────────────────────────────────────────────────────────
# GENERIRANJE TREE-a
# ─────────────────────────────────────────────────────────────────────────────

build_tree() {
  if command -v tree &>/dev/null; then
    local skip_pattern
    skip_pattern=$(IFS="|"; echo "${SKIP_DIRS[*]}")
    tree "$PROJECT_DIR" \
      -I "$skip_pattern" \
      --noreport \
      -a \
      2>/dev/null | head -80
  else
    # Fallback: ručni tree
    find "$PROJECT_DIR" \
      -not -path "*/.git/*" \
      -not -path "*/node_modules/*" \
      -not -path "*/__pycache__/*" \
      -not -path "*/.venv/*" \
      -not -path "*/venv/*" \
      -not -name "*.pyc" \
      | sed "s|$PROJECT_DIR/||" \
      | sort \
      | head -80
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# GLAVNI OUTPUT
# ─────────────────────────────────────────────────────────────────────────────

echo "[INFO] Projekat: $PROJECT_DIR"
echo "[INFO] Output:   $OUT  (Downloads)"
echo ""

{
  echo "# Project Snapshot: $PROJECT_NAME"
  echo "Generated: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "Path: $PROJECT_DIR"
  echo ""

  # ── Struktura ─────────────────────────────────────────────────────────────
  echo "## STRUCTURE"
  echo '```'
  build_tree
  echo '```'
  echo ""

  # ── Metadata (stats) ──────────────────────────────────────────────────────
  echo "## METADATA"
  total_py=$(find "$PROJECT_DIR" -name "*.py" \
    -not -path "*/__pycache__/*" \
    -not -path "*/.venv/*" \
    -not -path "*/venv/*" 2>/dev/null | wc -l | tr -d ' ')
  total_js=$(find "$PROJECT_DIR" \( -name "*.js" -o -name "*.ts" \) \
    -not -path "*/node_modules/*" 2>/dev/null | wc -l | tr -d ' ')
  echo "- Python fajlova: $total_py"
  echo "- JS/TS fajlova:  $total_js"
  echo ""

  # ── Session context (placeholder) ─────────────────────────────────────────
  echo "## SESSION GOAL"
  echo "_TODO: Popuni prije slanja — šta hoćeš da Claude uradi u ovoj sesiji._"
  echo ""
  echo "## KNOWN ISSUES"
  echo "_TODO: Navedi poznate probleme._"
  echo ""
  echo "## LAST CHANGE"
  echo "_TODO: Šta je zadnji put mijenjano._"
  echo ""

  # ── Sadržaj fajlova ───────────────────────────────────────────────────────
  echo "## FILES"
  echo ""

} > "$TMPFILE"

total_written=0
file_count=0
skipped_count=0
truncated_count=0

while IFS= read -r filepath; do
  # Skip provjere
  should_skip_file "$filepath" && { ((skipped_count++)) || true; continue; }

  # Relativna putanja
  relpath="${filepath#$PROJECT_DIR/}"

  # Veličina
  fsize=$(wc -c < "$filepath" 2>/dev/null || echo 0)

  # Skip praznih
  [ "$fsize" -eq 0 ] && continue

  # Ukupni limit
  if [ "$total_written" -gt "$MAX_TOTAL_BYTES" ]; then
    echo "" >> "$TMPFILE"
    echo "## TRUNCATED" >> "$TMPFILE"
    echo "_Snapshot prekinut na ${MAX_TOTAL_BYTES}B. Ostali fajlovi:_" >> "$TMPFILE"
    # Nabroji ostatak
    while IFS= read -r remaining; do
      should_skip_file "$remaining" && continue
      echo "- ${remaining#$PROJECT_DIR/}" >> "$TMPFILE"
    done
    break
  fi

  lang=$(get_lang "$filepath")
  hsize=$(human_size "$fsize")

  {
    echo "### $relpath ($hsize)"
    echo '```'"$lang"
    if [ "$fsize" -gt "$MAX_FILE_BYTES" ]; then
      head -c "$MAX_FILE_BYTES" "$filepath"
      echo ""
      echo "... [TRUNCATED — $(human_size $fsize) total, prikazano $(human_size $MAX_FILE_BYTES)]"
      ((truncated_count++)) || true
    else
      cat "$filepath"
    fi
    echo '```'
    echo ""
  } >> "$TMPFILE"

  ((total_written += fsize)) || true
  ((file_count++)) || true

done < <(collect_files)

# Finalni stats header
{
  echo ""
  echo "---"
  echo "_Snapshot stats: $file_count fajlova | $(human_size $total_written) | $skipped_count preskočeno | $truncated_count trunckirano_"
} >> "$TMPFILE"

mv "$TMPFILE" "$OUT"

echo "[DONE] $OUT"
echo "       Fajlova:     $file_count"
echo "       Veličina:    $(human_size $total_written)"
echo "       Preskočeno:  $skipped_count"
echo "       Trunckirano: $truncated_count"
echo ""
echo "       Prije slanja — popuni TODO sekcije u $OUT:"
echo "       ## SESSION GOAL"
echo "       ## KNOWN ISSUES"
echo "       ## LAST CHANGE"
