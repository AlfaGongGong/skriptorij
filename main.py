from flask import Flask, render_template, jsonify, request, send_from_directory
import os
import re
import signal
import sys
import threading
import json
import time
import logging
import webbrowser
app = Flask(__name__, static_folder='static', template_folder='templates')
PORT = 8080
PROJECTS_ROOT = os.path.join(os.getcwd(), 'data')
os.makedirs(PROJECTS_ROOT, exist_ok=True)
SHARED_STATS = {'status': 'IDLE', 'active_engine': '---', 'current_file': '---', 'current_file_idx': 0, 'total_files': 0, 'current_chunk_idx': 0, 'total_file_chunks': 0, 'ok': '0 / 0', 'skipped': '0', 'pct': 0, 'est': '--:--:--', 'fleet_active': 0, 'fleet_cooling': 0, 'live_audit': 'Sistem spreman. Čekam inicijalizaciju...', 'output_file': '', 'stvarno_prevedeno': 0, 'spaseno_iz_checkpointa': 0}
SHARED_CONTROLS = {'pause': False, 'stop': False, 'reset': False}
_start_time = None
_start_pct = 0
try:
    from intro_ui import INTRO_HTML
    _INTRO_LOADED = True
except ImportError:
    INTRO_HTML = ''
    _INTRO_LOADED = False

def secure_filename(filename: str) -> str:
    """Custom secure_filename s podrškom za balkanska slova."""
    if not filename:
        return 'nepoznato.epub'
    zamjene = {'č': 'c', 'ć': 'c', 'ž': 'z', 'š': 's', 'đ': 'dj', 'Č': 'C', 'Ć': 'C', 'Ž': 'Z', 'Š': 'S', 'Đ': 'Dj', ' ': '_'}
    for d, e in zamjene.items():
        filename = filename.replace(d, e)
    filename = os.path.basename(filename)
    filename = re.sub('[^a-zA-Z0-9_.\\-]', '_', filename)
    filename = re.sub('_+', '_', filename)
    return filename.strip('._-') or 'knjiga.epub'

def _safe_path(filename: str) -> str:
    """Vraća sigurnu apsolutnu putanju unutar PROJECTS_ROOT."""
    safe = secure_filename(filename)
    full = os.path.realpath(os.path.join(PROJECTS_ROOT, safe))
    if not full.startswith(os.path.realpath(PROJECTS_ROOT)):
        raise ValueError(f'Path traversal pokušaj: {filename}')
    return full

def reset_stats():
    global _start_time, _start_pct
    _start_time = None
    _start_pct = 0
    SHARED_STATS.update({'status': 'RESETOVANO', 'active_engine': '---', 'current_file': '---', 'current_file_idx': 0, 'total_files': 0, 'current_chunk_idx': 0, 'total_file_chunks': 0, 'ok': '0 / 0', 'skipped': '0', 'pct': 0, 'est': '--:--:--', 'fleet_active': 0, 'fleet_cooling': 0, 'live_audit': 'Sesija resetovana.\n', 'output_file': '', 'stvarno_prevedeno': 0, 'spaseno_iz_checkpointa': 0})
    SHARED_CONTROLS.update({'pause': False, 'stop': False, 'reset': False})

def _racunaj_eta():
    """Računa preostalo vrijeme na osnovu prosječne brzine od starta."""
    global _start_time, _start_pct
    pct = SHARED_STATS.get('pct', 0)
    if not _start_time or pct <= _start_pct or pct >= 100:
        return '--:--:--'
    elapsed = time.time() - _start_time
    done_pct = pct - _start_pct
    if done_pct <= 0:
        return '--:--:--'
    total_est = elapsed / (done_pct / 100.0)
    remaining = total_est - elapsed
    if remaining < 0:
        return 'Uskoro...'
    h = int(remaining // 3600)
    m = int(remaining % 3600 // 60)
    s = int(remaining % 60)
    return f'{h:02d}:{m:02d}:{s:02d}'

@app.route('/')
def index():
    return render_template('index.html', introhtml=INTRO_HTML)

@app.route('/api/books')
def list_books():
    os.makedirs(PROJECTS_ROOT, exist_ok=True)
    files = sorted((f for f in os.listdir(PROJECTS_ROOT) if f.lower().endswith(('.epub', '.mobi'))))
    try:
        with open(os.path.join(PROJECTS_ROOT, 'last_book.json'), 'r') as f:
            last = json.load(f).get('last_book')
    except Exception:
        last = None
    return jsonify({'books': [{'name': f, 'path': f} for f in files], 'last_book': last})

@app.route('/api/upload_book', methods=['POST'])
def upload_book():
    if 'file' not in request.files:
        return (jsonify({'error': 'Nema fajla'}), 400)
    f = request.files['file']
    if not f.filename:
        return (jsonify({'error': 'Prazno ime fajla'}), 400)
    filename = secure_filename(f.filename)
    path = _safe_path(filename)
    f.save(path)
    return jsonify({'status': 'ok', 'name': filename})

@app.route('/api/dev_models')
def dev_models():
    """Čita modele iz dev_api.json — vraća provajdere + QUAD_CORE opciju."""
    try:
        with open('dev_api.json') as f:
            data = json.load(f)
        skip = {'EPUB_BACKGROUND', 'PROXIES', 'PROXIES_OFF'}
        models = ['QUAD_CORE'] + [k for k in data.keys() if k.upper() not in skip]
        return jsonify(models)
    except Exception:
        return jsonify(['QUAD_CORE', 'GEMINI', 'GROQ', 'CEREBRAS'])

@app.route('/api/status')
def get_status():
    """#10: Vraća kompletan status s ETA računanjem."""
    SHARED_STATS['est'] = _racunaj_eta()
    return jsonify(SHARED_STATS)

@app.route('/api/fleet')
def get_fleet():
    """Vraća detalje flote za Fleet Pool prikaz."""
    try:
        from api_fleet import FleetManager, get_active_fleet
        # Preferiraj aktivnu instancu koja prati stvarno stanje (cooldowns itd.)
        fm = get_active_fleet()
        if fm is None:
            fm = FleetManager(config_path='dev_api.json')
        return jsonify(fm.get_fleet_summary())
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)

@app.route('/api/start', methods=['POST'])
def start_processing():
    global _start_time, _start_pct
    try:
        data = request.get_json()
        if not data or 'book' not in data:
            return (jsonify({'error': 'Nije odabran fajl'}), 400)
        book = secure_filename(data['book'])
        model = data.get('model', 'QUAD_CORE')
        mode = data.get('mode', 'PREVOD').upper()
        book_path = _safe_path(book)
        if not os.path.exists(book_path):
            return (jsonify({'error': f"Fajl '{book}' ne postoji na serveru"}), 404)
        SHARED_CONTROLS.update({'pause': False, 'stop': False, 'reset': False})
        SHARED_STATS.update({'status': 'POKRETANJE...', 'current_file': book, 'active_engine': model, 'pct': 0, 'ok': '0 / 0', 'live_audit': f'Inicijalizacija za: {book}\n', 'output_file': ''})
        _start_time = time.time()
        _start_pct = 0
        try:
            with open(os.path.join(PROJECTS_ROOT, 'last_book.json'), 'w') as f:
                json.dump({'last_book': book}, f)
        except Exception:
            pass
        if mode == 'TTS':
            from tts import start_from_master as start_tts
            thread = threading.Thread(target=start_tts, args=(book_path, model, SHARED_STATS, SHARED_CONTROLS), daemon=True)
        else:
            from skriptorij import start_skriptorij_from_master
            thread = threading.Thread(target=start_skriptorij_from_master, args=(book_path, model, SHARED_STATS, SHARED_CONTROLS), daemon=True)
        thread.start()
        return jsonify({'status': 'Started', 'file': book, 'mode': mode})
    except ValueError as e:
        return (jsonify({'error': str(e)}), 400)
    except Exception as e:
        SHARED_STATS['status'] = 'GREŠKA PRI STARTU'
        return (jsonify({'error': str(e)}), 500)

@app.route('/api/download/<path:filename>')
def download_file(filename):
    safe = secure_filename(filename)
    full = os.path.realpath(os.path.join(PROJECTS_ROOT, safe))
    if not full.startswith(os.path.realpath(PROJECTS_ROOT)):
        return (jsonify({'error': 'Neispravan zahtjev'}), 400)
    if not os.path.exists(full):
        return (jsonify({'error': 'Fajl nije pronađen'}), 404)
    return send_from_directory(PROJECTS_ROOT, safe, as_attachment=True)

# ============================================================================
# #12: EXPORT REZULTATA — JSON i TXT izvještaji
# ============================================================================
@app.route('/api/export/<fmt>')
def export_result(fmt):
    """Generiše i skida izvještaj o prijevodu u JSON ili TXT formatu."""
    output_file = SHARED_STATS.get('output_file', '')
    if not output_file:
        return (jsonify({'error': 'Nema završenog prijevoda'}), 404)
    epub_path = os.path.join(PROJECTS_ROOT, secure_filename(output_file))
    if not os.path.exists(epub_path):
        return (jsonify({'error': 'EPUB fajl nije pronađen'}), 404)
    try:
        from export_manager import generate_json_report, generate_txt_report
        from flask import Response
        if fmt == 'json':
            data = generate_json_report(epub_path, SHARED_STATS)
            return Response(
                data,
                mimetype='application/json',
                headers={'Content-Disposition': f'attachment; filename=izvjestaj_{output_file}.json'}
            )
        elif fmt == 'txt':
            data = generate_txt_report(epub_path, SHARED_STATS)
            return Response(
                data,
                mimetype='text/plain; charset=utf-8',
                headers={'Content-Disposition': f'attachment; filename=izvjestaj_{output_file}.txt'}
            )
        else:
            return (jsonify({'error': f'Nepoznat format: {fmt}'}), 400)
    except Exception:
        return (jsonify({'error': 'Greška pri generiranju izvještaja'}), 500)
# ============================================================================
@app.route('/api/keys', methods=['GET'])
def list_keys():
    """Vraća listu provajdera i maskiran prikaz ključeva."""
    try:
        with open('dev_api.json', encoding='utf-8') as f:
            data = json.load(f)
        skip = {'EPUB_BACKGROUND', 'PROXIES', 'PROXIES_OFF'}
        result = {}
        for prov, val in data.items():
            if prov.upper() in skip:
                continue
            keys = val if isinstance(val, list) else val.get('keys', [])
            result[prov] = [f'...{k[-6:]}' if len(k) > 6 else '***' for k in keys if k]
        return jsonify(result)
    except FileNotFoundError:
        return jsonify({})
    except Exception:
        return (jsonify({'error': 'Greška pri čitanju konfiguracije'}), 500)

@app.route('/api/keys/<provider>', methods=['POST'])
def add_key(provider):
    """Dodaje novi API ključ za provajdera."""
    data = request.get_json()
    if not data or 'key' not in data:
        return (jsonify({'error': 'Nedostaje "key" polje'}), 400)
    new_key = data['key'].strip()
    if not new_key:
        return (jsonify({'error': 'Prazan ključ'}), 400)
    prov_upper = re.sub(r'[^A-Z0-9_]', '', provider.upper())
    if not prov_upper:
        return (jsonify({'error': 'Neispravan naziv provajdera'}), 400)
    try:
        config_path = 'dev_api.json'
        try:
            with open(config_path, encoding='utf-8') as f:
                cfg = json.load(f)
        except FileNotFoundError:
            cfg = {}
        if prov_upper not in cfg:
            cfg[prov_upper] = []
        existing = cfg[prov_upper] if isinstance(cfg[prov_upper], list) else cfg[prov_upper].get('keys', [])
        if new_key in existing:
            return (jsonify({'error': 'Ključ već postoji'}), 409)
        if isinstance(cfg[prov_upper], list):
            cfg[prov_upper].append(new_key)
        else:
            cfg[prov_upper].setdefault('keys', []).append(new_key)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        return jsonify({'status': 'ok', 'provider': prov_upper, 'masked': f'...{new_key[-6:]}'})
    except Exception:
        return (jsonify({'error': 'Greška pri dodavanju ključa'}), 500)

@app.route('/api/keys/<provider>/<int:idx>', methods=['DELETE'])
def delete_key(provider, idx):
    """Briše API ključ po indeksu za dati provajder."""
    prov_upper = re.sub(r'[^A-Z0-9_]', '', provider.upper())
    try:
        config_path = 'dev_api.json'
        with open(config_path, encoding='utf-8') as f:
            cfg = json.load(f)
        if prov_upper not in cfg:
            return (jsonify({'error': 'Provajder ne postoji'}), 404)
        keys_list = cfg[prov_upper] if isinstance(cfg[prov_upper], list) else cfg[prov_upper].get('keys', [])
        if idx < 0 or idx >= len(keys_list):
            return (jsonify({'error': 'Indeks van opsega'}), 400)
        keys_list.pop(idx)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        return jsonify({'status': 'ok', 'provider': prov_upper})
    except Exception:
        return (jsonify({'error': 'Greška pri brisanju ključa'}), 500)

@app.route('/control/<action>', methods=['POST'])
def control_process(action):
    if action == 'pause':
        SHARED_CONTROLS['pause'] = True
        SHARED_STATS['status'] = 'PAUZIRANO'
    elif action == 'resume':
        SHARED_CONTROLS['pause'] = False
        SHARED_STATS['status'] = 'OBRADA U TOKU...'
    elif action == 'stop':
        SHARED_CONTROLS['stop'] = True
        SHARED_STATS['status'] = 'ZAUSTAVLJENO'
    elif action == 'reset':
        SHARED_CONTROLS['reset'] = True
        reset_stats()
    else:
        return (jsonify({'error': f'Nepoznata akcija: {action}'}), 400)
    return jsonify({'status': 'ok', 'action': action})

# ============================================================================
# #9: ELEGANTNA TERMINACIJA — signal handling
# ============================================================================
def _graceful_shutdown(signum, frame):
    """Postavi stop flag i čekaj da aktivna obrada završi čišćenje."""
    SHARED_CONTROLS['stop'] = True
    SHARED_STATS['status'] = 'ZAUSTAVLJENO'
    print('\n\x1b[1;93m[SHUTDOWN] Signal primljen — čekam završetak tekuće obrade...\x1b[0m')
    sys.exit(0)

if __name__ == '__main__':
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    os.system('clear' if os.name == 'posix' else 'cls')
    # #9: Registriraj signal handlere za graceful shutdown
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT, _graceful_shutdown)
    print('\x1b[1;91m  ____  _         _       _             _ _ \x1b[0m')
    print('\x1b[1;91m / ___|| | ___ __(_)_ __ | |_ ___  _ __(_) |\x1b[0m')
    print("\x1b[1;91m \\___ \\| |/ / '__| | '_ \\| __/ _ \\| '__| | |\x1b[0m")
    print('\x1b[1;91m  ___) |   <| |  | | |_) | || (_) | |  | | |\x1b[0m')
    print('\x1b[1;91m |____/|_|\\_\\_|  |_| .__/ \\__\\___/|_|  |_| |\x1b[0m')
    print('\x1b[1;91m                   |_|                      \x1b[0m')
    print('\x1b[1;92m' + '=' * 48 + '\x1b[0m')
    print('\x1b[1;96m  🚀 SKRIPTORIJ V8 TURBO - SERVER AKTIVAN 🚀  \x1b[0m')
    print('\x1b[1;92m' + '=' * 48 + '\x1b[0m')
    print(f'\x1b[1;93m [INFO]\x1b[0m http://127.0.0.1:{PORT}')
    if _INTRO_LOADED:
        print('\x1b[1;95m [INFO] Kinematski intro: AKTIVAN\x1b[0m')
    print('\n\x1b[1;31m >>> CTRL+C za zaustavljanje <<<\x1b[0m\n')

    def open_browser():
        time.sleep(1.5)
        try:
            if os.path.exists('/data/data/com.termux/files/usr/bin/termux-open-url'):
                os.system(f'termux-open-url http://127.0.0.1:{PORT} > /dev/null 2>&1')
            else:
                webbrowser.open(f'http://127.0.0.1:{PORT}')
        except Exception:
            pass
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)