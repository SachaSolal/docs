# 03-assets — Génération Visuelle & Audio

Ce module gère la génération des images via ComfyUI (SDXL + IP-Adapter)
et la voix off via F5-TTS ou Kokoro-TTS.

## Structure

```
/03-assets/
  /prompts-images/    ← prompts SDXL extraits du script JSON
  /raw-images/        ← images PNG générées par ComfyUI
  /voice-overs/       ← fichiers .mp3 générés par TTS
```

---

## Stratégie de cohérence visuelle — IP-Adapter

### Le problème
Pour les femmes peu documentées (peu ou pas de portraits connus),
Stable Diffusion génère un personnage différent à chaque image.
Résultat : le visage change entre les séquences → effet amateur immédiat.

### La solution : IP-Adapter avec image de référence

```
Séquence 1 (obligatoire) : Portrait neutre du personnage
  → Prompt : "portrait of a [époque] woman, neutral background,
               Rembrandt lighting, photorealistic, detailed face"
  → Cette image devient LA référence pour toutes les séquences suivantes

Séquences 2-N : IP-Adapter injecte la référence
  → IP-Adapter weight : 0.55-0.65 (trop haut = personnage figé,
                                    trop bas = incohérence)
  → ControlNet OpenPose : cohérence de posture/cadrage
  → Style LoRA : cohérence artistique (baroque_painting, renaissance_portrait)
```

### Workflow ComfyUI recommandé

```
[Load Image] référence_portrait.png
      |
      v
[IP-Adapter] weight=0.6, noise=0.05
      |
[SDXL Checkpoint] (DreamShaper XL ou Juggernaut XL)
      |
[ControlNet OpenPose] (si scène avec personnage debout/assis)
      |
[KSampler] steps=25, cfg=7, sampler=dpmpp_2m
      |
[VAE Decode] → PNG 1024x1024
```

### Cas particulier : personnage sans aucun portrait historique

```python
PORTRAIT_PROMPT_TEMPLATE = """
{période} woman, {origine_ethnique}, {âge_approximatif} years old,
historical portrait style, {lighting},
wearing period-appropriate {vêtements_époque},
dignified expression, strong presence,
masterpiece quality, 8k, detailed
Negative: modern, anachronistic, cartoon, deformed
"""

# L'important : garder EXACTEMENT le même prompt de base
# pour la séquence 1, et ne varier que la scène pour les suivantes
# IP-Adapter fera le reste pour la cohérence du visage
```

---

## Génération Audio — F5-TTS / Kokoro-TTS

### Clonage vocal

```python
# F5-TTS (recommandé pour qualité)
from f5_tts import TTS

tts = TTS(voice_sample="./config/ma_voix_reference.wav")

# Les [PAUSE_1S] du script sont convertis en silences réels
def generate_voiceover(narration_text: str, output_path: str):
    # Remplacer les tags par des marqueurs silences
    text = narration_text.replace("[PAUSE_1S]", "...")
    tts.generate(text, output=output_path, speed=0.95)
```

### Sound Design (critique pour la qualité perçue)

```python
# Ajouter room tone + SFX sous la voix off
# Via FFmpeg après génération TTS :

def add_sound_design(voiceover: str, sfx_type: str, output: str):
    # sfx_type déterminé par l'emotion_tag du script
    sfx_map = {
        "tension":    "sfx/wind_howling.mp3",
        "triomphe":   "sfx/crowd_distant.mp3",
        "deuil":      "sfx/rain_soft.mp3",
        "révélation": "sfx/room_tone_church.mp3",
    }
    sfx = sfx_map.get(sfx_type, "sfx/room_tone_neutral.mp3")

    cmd = (
        f'ffmpeg -i "{voiceover}" -i "{sfx}" '
        f'-filter_complex "[1:a]volume=0.08[sfx];[0:a][sfx]amix=inputs=2" '
        f'"{output}"'
    )
    subprocess.run(cmd, shell=True, check=True)
```

---

## Communication avec n8n (FastAPI)

ComfyUI peut prendre 5-15 min pour 8-10 images SDXL.
Le worker expose une API pour éviter les timeouts n8n :

```python
# Dans le worker FastAPI (port 5000) :

@app.post("/generate-images")
async def generate_images(job: dict):
    job_id = job["slug"]
    db.update_status(job_id, "generating_images")
    background_tasks.add_task(run_comfyui_pipeline, job)
    return {"status": "started", "job_id": job_id}

@app.get("/status/{job_id}")
def get_status(job_id: str):
    return db.get_status(job_id)
```

n8n poll `GET /status/{slug}` toutes les 60s (max 20 tentatives = 20 min).
