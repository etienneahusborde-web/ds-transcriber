"""Service web DS2 -> WAV -> transcription Whisper (prototype Render)."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

app = Flask(
    __name__,
    template_folder=".",
    static_folder=".",
    static_url_path="/static"
)
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_UPLOAD_MB', '12')) * 1024 * 1024
app.config['JSON_AS_ASCII'] = False

DECODER = os.getenv('DSS_DECODER', '/usr/local/bin/dss-decode')
WHISPER = os.getenv('WHISPER_CLI', '/usr/local/bin/whisper-cli')
MODEL = os.getenv('WHISPER_MODEL', '/opt/models/ggml-tiny.bin')
MAX_AUDIO_SECONDS = int(os.getenv('MAX_AUDIO_SECONDS', '600'))
JOB_TTL_SECONDS = int(os.getenv('JOB_TTL_SECONDS', '1800'))
TRANSCRIPTION_TIMEOUT = int(os.getenv('TRANSCRIPTION_TIMEOUT', '1200'))
THREADS = max(1, min(int(os.getenv('WHISPER_THREADS', '2')), 4))

jobs: dict[str, dict] = {}
lock = threading.RLock()
active = threading.Semaphore(1)


def clean_expired():
    now = time.monotonic()
    with lock:
        expired = [key for key, j in jobs.items() if j['status'] in ('done', 'error') and now - j['updated'] > JOB_TTL_SECONDS]
        for key in expired:
            job = jobs.pop(key)
            shutil.rmtree(job['directory'], ignore_errors=True)


def set_state(job_id: str, **changes):
    with lock:
        if job_id in jobs:
            jobs[job_id].update(changes, updated=time.monotonic())


def run_command(args: list[str], timeout: int) -> None:
    result = subprocess.run(args, capture_output=True, text=True, errors='replace', timeout=timeout, check=False)
    if result.returncode != 0:
        # Ne pas exposer les chemins complets, les données privées ou les logs du moteur.
        raise RuntimeError(f'Commande de traitement interrompue (code {result.returncode}).')


def process(job_id: str):
    with lock:
        directory = jobs[job_id]['directory']
        source = jobs[job_id]['source']
    try:
        set_state(job_id, status='processing', step='Conversion du fichier audio…')
        raw_wav = directory / 'original.wav'
        wav = directory / 'audio.wav'
        run_command([DECODER, '-O', str(raw_wav), str(source)], timeout=90)

        set_state(job_id, step='Préparation audio pour Whisper…')
        run_command(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(raw_wav),
                     '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le', str(wav)], timeout=90)
        raw_wav.unlink(missing_ok=True)
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                '-of', 'default=noprint_wrappers=1:nokey=1', str(wav)],
                               capture_output=True, text=True, timeout=15, check=True)
        duration = float(probe.stdout.strip())
        if not 0 < duration <= MAX_AUDIO_SECONDS:
            raise ValueError(f'Enregistrement trop long : maximum {MAX_AUDIO_SECONDS // 60} minutes.')

        set_state(job_id, step='Transcription en cours (cela peut prendre plusieurs minutes)…')
        output_base = directory / 'transcription'
        run_command([WHISPER, '-m', MODEL, '-f', str(wav), '-l', 'fr', '-otxt', '-osrt',
                     '-of', str(output_base), '-t', str(THREADS), '-np'], timeout=TRANSCRIPTION_TIMEOUT)
        txt, srt = directory / 'transcription.txt', directory / 'transcription.srt'
        if not txt.exists() or not srt.exists():
            raise RuntimeError('Whisper n’a pas créé les fichiers attendus.')
        set_state(job_id, status='done', step='Transcription terminée', text=txt.read_text(encoding='utf-8', errors='replace')[:100000])
    except subprocess.TimeoutExpired:
        set_state(job_id, status='error', step='Le traitement a dépassé le temps autorisé.')
    except (ValueError, RuntimeError) as exc:
        set_state(job_id, status='error', step=str(exc))
    except Exception:
        app.logger.exception('Erreur pendant le traitement %s', job_id)
        set_state(job_id, status='error', step='Échec du traitement du fichier.')
    finally:
        source.unlink(missing_ok=True)
        active.release()


@app.get('/')
def home():
    clean_expired()
    return render_template('index.html', max_mb=app.config['MAX_CONTENT_LENGTH'] // 1024 // 1024,
                           max_minutes=MAX_AUDIO_SECONDS // 60)


@app.get('/health')
def health():
    return 'ok', 200


@app.post('/api/jobs')
def create_job():
    clean_expired()
    uploaded = request.files.get('file')
    if not uploaded or not uploaded.filename:
        return jsonify(error='Sélectionnez un fichier DS2 ou DSS.'), 400
    if Path(uploaded.filename).suffix.lower() not in ('.ds2', '.dss'):
        return jsonify(error='Seuls les fichiers .ds2 et .dss sont acceptés.'), 400
    if not active.acquire(blocking=False):
        return jsonify(error='Une transcription est déjà en cours. Réessayez plus tard.'), 429
    directory = None
    try:
        directory = Path(tempfile.mkdtemp(prefix='ds2_'))
        filename = 'source' + Path(uploaded.filename).suffix.lower()
        source = directory / filename
        uploaded.save(source)
        if source.stat().st_size == 0:
            raise ValueError('Le fichier est vide.')
        job_id = uuid.uuid4().hex
        with lock:
            jobs[job_id] = dict(directory=directory, source=source, status='queued',
                                step='Démarrage…', text='', updated=time.monotonic())
        threading.Thread(target=process, args=(job_id,), daemon=True).start()
        return jsonify(id=job_id), 202
    except (OSError, ValueError) as exc:
        if directory:
            shutil.rmtree(directory, ignore_errors=True)
        active.release()
        return jsonify(error=str(exc)), 400
    except Exception:
        if directory:
            shutil.rmtree(directory, ignore_errors=True)
        active.release()
        raise


@app.get('/api/jobs/<job_id>')
def status(job_id):
    clean_expired()
    with lock:
        job = jobs.get(job_id)
        if job is None:
            abort(404)
        return jsonify(status=job['status'], step=job['step'], text=job['text'] if job['status'] == 'done' else '')


@app.get('/api/jobs/<job_id>/download/<kind>')
def download(job_id, kind):
    clean_expired()
    mapping = {'wav': ('audio.wav', 'audio/wav'), 'txt': ('transcription.txt', 'text/plain'),
               'srt': ('transcription.srt', 'application/x-subrip')}
    if kind not in mapping:
        abort(404)
    with lock:
        job = jobs.get(job_id)
        if job is None or job['status'] != 'done':
            abort(404)
        name, mime = mapping[kind]
        path = job['directory'] / name
    if not path.is_file():
        abort(404)
    return send_file(path, as_attachment=True, download_name=name, mimetype=mime)


@app.errorhandler(RequestEntityTooLarge)
def too_large(_):
    return jsonify(error='Fichier trop volumineux pour cette version.'), 413


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)
