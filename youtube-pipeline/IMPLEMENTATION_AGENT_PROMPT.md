# Prompt Agent IA — Implémentation des briques manquantes
# Pipeline YouTube : Femmes Historiques Oubliées

---

## Contexte

Tu travailles sur un pipeline Python d'automatisation YouTube déjà partiellement implémenté.
Le code existant se trouve dans `youtube-pipeline/`.

Structure actuelle :
```
youtube-pipeline/
  config/db_setup.py          ← SQLite setup (status.db)
  01-research/fetch_data.py   ← Wikipedia + retry 429
  02-scripts/generator.py     ← Gemini 2 passes + JSON
  03-assets/generate_audio.py ← F5-TTS (AMD/DirectML)
  03-assets/asset_selector.py ← images archive-first
  04-edit/editor.py           ← FFmpeg Ken Burns + grain
  05-upload/uploader.py       ← YouTube OAuth 2.0
  api/main.py                 ← FastAPI + lock + quota
  config/status.db            ← SQLite état pipeline
```

**GPU : AMD Radeon RX 7700 XT (Windows, DirectML)**
**LLM : Gemini API free tier**
**Orchestrateur : n8n local**

---

## Ta mission : implémenter 8 briques dans l'ordre exact ci-dessous

---

### BRIQUE 1 — Fix VRAM AMD : F5-TTS en subprocess isolé

**Fichier à modifier** : `03-assets/generate_audio.py`

**Problème** : `torch.cuda.empty_cache()` ne fonctionne pas sur AMD.
La seule solution fiable est d'isoler F5-TTS dans un subprocess Python
qui libère toute la VRAM à sa mort.

**Implémentation** :
1. Crée `03-assets/run_tts_worker.py` — script standalone qui :
   - Reçoit le texte via argument `--text` et `--output`
   - Charge F5-TTS, génère le fichier audio, se termine
   - Remplace les `[PAUSE_1S]` par 1 seconde de silence réel (FFmpeg ou pydub)

2. Modifie `generate_audio.py` pour appeler ce worker via subprocess :
```python
import subprocess, sys

def generate_audio_isolated(text: str, output_path: str, timeout: int = 300) -> bool:
    result = subprocess.run(
        [sys.executable, "03-assets/run_tts_worker.py",
         "--text", text, "--output", output_path],
        capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        logger.error(f"TTS failed: {result.stderr}")
        return False
    return True
```

**Test** : `python 03-assets/generate_audio.py --name "Marie Curie" --text "Elle a changé le monde."`

---

### BRIQUE 2 — File d'attente des sujets (queue)

**Fichier à modifier** : `config/db_setup.py`

**Ajout** : une table `queue` dans SQLite :
```sql
CREATE TABLE IF NOT EXISTS queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    priority    INTEGER DEFAULT 5,
    notes       TEXT,
    added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status      TEXT DEFAULT 'pending'
    -- pending | processing | done | skipped
);
```

**Crée** `config/queue_manager.py` avec ces fonctions :
```python
def add_subject(name: str, priority: int = 5, notes: str = "") -> bool:
    """Ajoute un sujet. Retourne False si déjà présent."""

def get_next_subject() -> dict | None:
    """Retourne le prochain sujet pending par priorité DESC, ou None."""

def mark_processing(name: str) -> None:
    """Marque un sujet comme en cours de traitement."""

def mark_done(name: str) -> None:
    """Marque un sujet comme terminé."""

def list_queue() -> list[dict]:
    """Retourne toute la queue avec statuts."""
```

**Ajoute dans `api/main.py`** ces endpoints :
- `POST /queue/add` — body: `{"name": "...", "priority": 5, "notes": "..."}`
- `GET /queue/next` — retourne le prochain sujet à traiter
- `GET /queue/list` — liste complète

**Pré-remplissage** : insère ces 10 sujets par défaut dans la queue au setup :
```
Hedy Lamarr, Lise Meitner, Rosalind Franklin, Nzinga du Ndongo,
Émilie du Châtelet, Cecilia Payne-Gaposchkin, Chien-Shiung Wu,
Mariam al-Astrolabiya, Hypatia d'Alexandrie, Mileva Maric
```

---

### BRIQUE 3 — Détection de doublons

**Fichier à modifier** : `api/main.py` et `config/queue_manager.py`

Avant tout nouveau run, vérifie dans les deux tables (`subjects` ET `queue`) :
```python
def is_duplicate(name: str) -> tuple[bool, str]:
    """
    Retourne (True, raison) si le sujet a déjà été traité ou est en cours.
    Vérifie subjects.status IN ('done', 'uploading', 'editing', 'approved')
    ET queue.status = 'processing'
    """
```

Ajoute cette vérification au début du endpoint principal `/run` dans `api/main.py`.
Si doublon → retourne HTTP 409 avec `{"error": "duplicate", "existing_status": "..."}`.

---

### BRIQUE 4 — Vérification espace disque

**Fichier à créer** : `config/system_checks.py`

```python
import shutil
import structlog

log = structlog.get_logger()

def check_disk_space(min_gb: float = 5.0, path: str = ".") -> bool:
    """
    Vérifie que l'espace disque disponible >= min_gb.
    Logge un warning et retourne False si insuffisant.
    """
    free_gb = shutil.disk_usage(path).free / (1024 ** 3)
    if free_gb < min_gb:
        log.warning("disk_space_low", free_gb=round(free_gb, 2), min_gb=min_gb)
        return False
    log.info("disk_space_ok", free_gb=round(free_gb, 2))
    return True

def check_all() -> dict:
    """
    Retourne un dict avec tous les checks système :
    disk_ok, db_accessible, gemini_quota_reset_in (estimation), gpu_info
    """
```

**Intégration** : appelle `check_disk_space()` au début de chaque run dans `api/main.py`.
Si False → arrêter le run, retourner HTTP 507.

---

### BRIQUE 5 — Validation MP4 avant upload

**Fichier à modifier** : `05-upload/uploader.py`

Ajoute cette fonction et appelle-la AVANT `upload_video()` :

```python
import subprocess

def validate_video(path: str, min_duration_sec: float = 10.0) -> tuple[bool, str]:
    """
    Vérifie que le fichier MP4 est valide et a une durée suffisante.
    Retourne (True, "ok") ou (False, "raison de l'échec").
    """
    # 1. Fichier existe et taille > 1 Mo
    if not os.path.exists(path):
        return False, "file_not_found"
    if os.path.getsize(path) < 1_000_000:
        return False, "file_too_small"

    # 2. FFprobe vérifie la durée
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=30
    )
    try:
        duration = float(result.stdout.strip())
        if duration < min_duration_sec:
            return False, f"duration_too_short_{duration:.1f}s"
    except ValueError:
        return False, "ffprobe_parse_error"

    # 3. Vérifie qu'il y a bien une piste vidéo ET une piste audio
    result2 = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=30
    )
    if "video" not in result2.stdout:
        return False, "no_video_stream"

    return True, "ok"
```

Si la validation échoue → status SQLite = `"error"`, message d'erreur logué, PAS d'upload.

---

### BRIQUE 6 — Thumbnail Factory

**Fichier à créer** : `03-assets/generate_thumbnail.py`

Génère une thumbnail YouTube (1280x720) en 3 étapes :

**Étape A** : sélectionne ou génère l'image de base
- Cherche d'abord dans `03-assets/raw-images/{slug}/` la meilleure image (portrait)
- Si aucune disponible : utilise ComfyUI API (`http://comfyui:8188`) avec le prompt SDXL du script

**Étape B** : composition avec Pillow
```python
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

def create_thumbnail(
    base_image_path: str,
    subject_name: str,
    subtitle: str,        # ex: "La mathématicienne oubliée"
    output_path: str,
    style: str = "dark"   # "dark" | "vintage" | "dramatic"
) -> str:
    """
    Crée une thumbnail YouTube 1280x720 :
    - Image de base redimensionnée + recadrée
    - Gradient sombre en bas (lisibilité du texte)
    - Nom du personnage en grand (police d'époque si disponible)
    - Sous-titre en plus petit
    - Boost contraste +30% (améliore le CTR)
    - Optionnel : bord doré ou effet vignette
    Retourne le chemin du fichier généré.
    """
```

**Étape C** : intègre dans le pipeline
- Appel dans `main.py` après `stage_assets()`, avant `stage_edit()`
- La thumbnail est sauvegardée dans `03-assets/thumbnails/{slug}.jpg`
- `uploader.py` l'utilise automatiquement si le fichier existe

**Polices** : télécharge et inclut dans `assets/fonts/` :
- `Cinzel-Regular.ttf` (Google Fonts, libre, style romain/époque)
- Fallback : `Arial Bold` si Cinzel absent

---

### BRIQUE 7 — Endpoint /health amélioré

**Fichier à modifier** : `api/main.py`

Remplace ou complète le `/health` existant :

```python
@app.get("/health")
async def health_check():
    """
    Retourne l'état complet du système pour le monitoring n8n.
    """
    return {
        "status": "ok" | "degraded" | "critical",
        "checks": {
            "database": bool,           # SQLite accessible
            "disk_free_gb": float,      # espace disque disponible
            "disk_ok": bool,            # >= 5 Go
            "comfyui_reachable": bool,  # GET http://comfyui:8188/ répond
            "last_run": {
                "slug": str | None,
                "status": str | None,
                "completed_at": str | None
            },
            "queue_pending_count": int, # sujets en attente
            "queue_next": str | None    # prochain sujet
        },
        "timestamp": "ISO8601"
    }
```

Règle : `status = "critical"` si `disk_ok=False` ou `database=False`.
`status = "degraded"` si `comfyui_reachable=False`.

---

### BRIQUE 8 — Rotation logs + nettoyage automatique

**Fichier à créer** : `config/cleanup.py`

```python
def cleanup_old_exports(keep_last_n: int = 10) -> int:
    """
    Supprime les anciens exports MP4 et leurs raw-images associées.
    Garde les N plus récents. Retourne le nombre de fichiers supprimés.
    """

def cleanup_old_logs(keep_days: int = 30) -> int:
    """
    Supprime les fichiers de log de plus de keep_days jours.
    """

def backup_database(backup_dir: str = "config/backups") -> str:
    """
    Copie status.db avec timestamp. Garde les 7 dernières sauvegardes.
    Retourne le chemin du backup créé.
    """

def run_all_cleanups() -> dict:
    """Lance tous les nettoyages et retourne un rapport."""
```

**Intégration** :
- Ajoute `POST /maintenance/cleanup` dans `api/main.py` (appelle `run_all_cleanups()`)
- Dans n8n : un second CRON (1x/semaine, le dimanche) appelle ce endpoint

---

## Règles d'implémentation

1. **Ne casse rien** : chaque brique est additive. Ne modifie pas la logique existante des modules, ajoute seulement.

2. **SQLite thread-safe** : utilise `check_same_thread=False` et un `threading.Lock()` pour tous les accès concurrents.

3. **Logs partout** : chaque fonction nouvelle doit logger avec structlog :
   ```python
   log.info("action_done", module="brique_X", slug=slug, duration_sec=X)
   log.error("action_failed", module="brique_X", error=str(e))
   ```

4. **Gestion d'erreurs** : chaque fonction retourne `bool` ou `tuple[bool, str]`.
   Jamais de `raise` non capturé qui tue le pipeline entier.

5. **Requirements** : ajoute les nouvelles dépendances dans `requirements.txt` avec versions fixes.
   Nouvelles libs probables : `Pillow>=10.0.0`, `pydub>=0.25.0`

6. **Tests** : après chaque brique, fournis une commande de test minimale.

---

## Ordre d'exécution

Implémente dans cet ordre strict (chaque brique dépend de la précédente) :
```
BRIQUE 2 (queue) → BRIQUE 3 (doublons) → BRIQUE 4 (disque)
→ BRIQUE 1 (VRAM) → BRIQUE 5 (validation MP4) → BRIQUE 6 (thumbnail)
→ BRIQUE 7 (health) → BRIQUE 8 (cleanup)
```

---

## Validation finale

Une fois toutes les briques implémentées, exécute ce scénario de test complet :

```bash
# 1. Vérifier la queue
curl http://localhost:8000/queue/list

# 2. Vérifier le health
curl http://localhost:8000/health

# 3. Lancer un run complet sur "Hedy Lamarr"
curl http://localhost:8000/poc/Hedy%20Lamarr

# 4. Vérifier le statut
curl http://localhost:8000/status/hedy-lamarr

# 5. Lancer le cleanup
curl -X POST http://localhost:8000/maintenance/cleanup
```

Tous ces appels doivent retourner HTTP 200 sans erreur.
