# 04-edit — Montage Vidéo

Assemblage FFmpeg des images, voix off, sous-titres et effets visuels.
Les transitions et effets sont déterminés automatiquement par l'emotion_tag du script.

## Stack technique

- **FFmpeg** (via subprocess Python) — moteur principal, plus rapide que MoviePy
- **faster-whisper** — génération des sous-titres (4-8x plus rapide que whisper)
- **librosa** — détection des silences pour caler les cuts
- **Pillow + numpy** — animation des sous-titres mot par mot

## Flux de montage

```
[Input]
  /03-assets/raw-images/{slug}/*.png   (images SDXL)
  /03-assets/voice-overs/{slug}.mp3    (voix off + sound design)
  /02-scripts/approved/{slug}.json     (script avec emotion_tag + transition_type)
      |
      v
[1] Détection silences (librosa) → timestamps de cut
      |
      v
[2] Ken Burns par image (FFmpeg zoompan, point focal aléatoire)
      |
      v
[3] Assemblage clips selon transition_type par séquence
      |
      v
[4] Mixage audio (voix off + musique de fond)
      |
      v
[5] Sous-titres faster-whisper → animation mot par mot
      |
      v
[6] Export final 1080x1920 (format Shorts) ou 1920x1080 (format long)
      |
[Output] /04-edit/exports/{slug}.mp4
```

## Ken Burns dynamique (FFmpeg corrigé)

```python
import subprocess
import random

def apply_ken_burns(input_img: str, output_video: str,
                    duration: int = 5, zoom_speed: float = 0.002,
                    shake: int = 8) -> None:
    """
    Ken Burns avec point focal aléatoire et shake humanisé.
    Évite le zoom centré identique sur chaque image (effet diaporama).
    """
    # Variation du point focal selon la composition de l'image
    focal_x = random.uniform(0.35, 0.65)
    focal_y = random.uniform(0.30, 0.60)

    cmd = (
        f'ffmpeg -framerate 30 -loop 1 -i "{input_img}" '
        f'-vf "scale=iw*2:ih*2,'
        f'zoompan='
        f"z='min(zoom+{zoom_speed},1.5)':"
        f"x='iw*{focal_x}-(iw/zoom*{focal_x})+sin(random(0)*6.28)*{shake}':"
        f"y='ih*{focal_y}-(ih/zoom*{focal_y})+sin(random(1)*6.28)*{shake}':"
        f"d={duration*30}:fps=30:s=1080x1920\" "
        f'-c:v libx264 -t {duration} -pix_fmt yuv420p "{output_video}"'
    )
    subprocess.run(cmd, shell=True, check=True)
```

## Transitions par emotion_tag

```python
TRANSITION_MAP = {
    "tension":    "glitch",    # cut sec + frame freeze 2-3 frames
    "triomphe":   "zoom_in",   # zoom rapide vers le centre
    "deuil":      "dissolve",  # fondu enchaîné 1.5s
    "révélation": "fade_noir", # fondu noir 0.5s → nouvelle scène
    "colère":     "cut_sec",   # cut brutal sans transition
    "espoir":     "pan_left",  # panoramique gauche → droite
}
```

## Sous-titres animés (faster-whisper)

```python
from faster_whisper import WhisperModel

def generate_subtitles(audio_path: str, output_srt: str) -> None:
    model = WhisperModel("medium", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_path, word_timestamps=True)

    with open(output_srt, "w") as f:
        for i, segment in enumerate(segments):
            # Format SRT standard
            f.write(f"{i+1}\n")
            f.write(f"{format_time(segment.start)} --> {format_time(segment.end)}\n")
            f.write(f"{segment.text.strip()}\n\n")
```

## Format de sortie

| Format | Résolution | Usage |
|---|---|---|
| Shorts | 1080x1920 (9:16) | Acquisition nouveaux abonnés |
| Long | 1920x1080 (16:9) | Vidéo principale (8-12 min) |

Le format est défini dans le script JSON (`metadata.format`).
