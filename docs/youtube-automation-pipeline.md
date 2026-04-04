# Pipeline YouTube Automatisé — Architecture V3

> Chaîne YouTube dédiée aux biographies de femmes historiques oubliées
> Objectif : 1 vidéo/semaine, zéro coût API, Python-driven

---

## Stack technique retenue

| Composant | Outil | Justification |
|---|---|---|
| Orchestration | n8n (self-hosted) | Visuel, gratuit, nodes YouTube natifs |
| LLM primaire | Gemini API (free tier) | Gratuit, qualité suffisante |
| LLM fallback | Ollama (Llama3 local) | Zéro coût, zéro limite |
| Retry/Robustesse | tenacity | Backoff exponentiel, gestion rate limits |
| Voix | F5-TTS ou Kokoro-TTS | Clonage vocal open source |
| Images | Stable Diffusion SDXL + ComfyUI | Déjà maîtrisé, API locale |
| Cohérence visuelle | IP-Adapter + ControlNet Reference | Même personnage sur toutes les scènes |
| Montage | FFmpeg (via Python subprocess) | Perf > MoviePy |
| Sous-titres | faster-whisper | 4-8x plus rapide que whisper standard |
| Upload | YouTube Data API v3 | Automatisation complète |
| Monitoring | structlog | Logging structuré pour debug prod |

---

## Architecture V3 — Pipeline complet

```
[TRIGGER] n8n cron (1x/semaine)
         |
         v
[1. RECHERCHE]
  Wikipedia API → résumé biographique
  + DuckDuckGo scraping → sources complémentaires
  + Fact-checking pass (Gemini) → JSON vérifié
         |
         v
[2. SCRIPT — 2 passes Gemini]
  Passe 1 : structure en 8 tableaux de 20s (JSON)
  Passe 2 : rédaction narrative (style BBC, Morgan Freeman)
  Output : JSON {sequence_id, narration, emotion_tag,
                 visual_prompt, transition_type, [PAUSE_1S]}
  Fallback : Ollama Llama3 si rate limit Gemini
  Cache : fichier JSON local par sujet (évite re-génération)
         |
         v
[3. VOIX OFF]
  F5-TTS / Kokoro-TTS → clonage vocal → .mp3
  + Room tone (bruit de fond ambiant)
  + SFX contextuels (vent, parchemin, feu)
         |
         v
[4. IMAGES — ComfyUI API locale]
  Image 1 (portrait neutre) → référence IP-Adapter
  Images 2-N : SDXL + IP-Adapter (weight 0.6)
               + ControlNet OpenPose
               + Style LoRA (baroque_painting, renaissance)
  Lighting : Rembrandt / Chiaroscuro (dans les prompts SDXL)
         |
         v
[5. MONTAGE — FFmpeg]
  Ken Burns dynamique (point focal aléatoire, shake humanisé)
  Cuts calés sur les silences (librosa)
  Transitions selon emotion_tag (zoom_in, dissolve, glitch)
  Sous-titres animés mot par mot (Pillow + numpy)
  Grain de pellicule léger (overlay)
         |
         v
[6. UPLOAD YouTube]
  Métadonnées générées par Gemini
  Upload → attente 45s → mise à jour tags/description (2 appels séparés)
  Thumbnail : SDXL (visage + texte choc)
  Publication à heure variable
```

---

## Décisions techniques clés

### Robustesse API

```python
# Retry uniquement sur ResourceExhausted (pas sur erreurs 400)
from google.api_core.exceptions import ResourceExhausted
from tenacity import retry, retry_if_exception_type, wait_exponential, stop_after_attempt

@retry(
    retry=retry_if_exception_type(ResourceExhausted),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(5)
)
def call_gemini(prompt):
    model = genai.GenerativeModel('gemini-1.5-flash')
    return model.generate_content(prompt).text, "gemini"

def generate_script(prompt):
    try:
        return call_gemini(prompt)
    except Exception:
        # Fallback Ollama — flagué pour review manuelle
        response = ollama.generate(model='llama3', prompt=prompt)
        return response['response'], "ollama"  # source trackée
```

### Commande FFmpeg Ken Burns (corrigée)

```python
def apply_ken_burns(input_img, output_video, duration=5, zoom_speed=0.002, shake=8):
    cmd = (
        f'ffmpeg -framerate 30 -loop 1 -i "{input_img}" '
        f'-vf "scale=iw*2:ih*2,'
        f'zoompan='
        f'z=\'min(zoom+{zoom_speed},1.5)\':'
        f'x=\'iw/2-(iw/zoom/2)+sin(random(0)*6.28)*{shake}\':'
        f'y=\'ih/2-(ih/zoom/2)+sin(random(1)*6.28)*{shake}\':'
        f'd={duration*30}:fps=30:s=1080x1920" '
        f'-c:v libx264 -t {duration} -pix_fmt yuv420p "{output_video}"'
    )
    subprocess.run(cmd, shell=True, check=True)
```

### System Prompt Gemini (format JSON narratif)

```json
{
  "role": "Directeur de création - Documentaires Premium",
  "style": "Cinématique, sombre, focalisé sur l injustice et la résilience",
  "instructions": [
    "Interdiction d adjectifs clichés (incroyable, magnifique).",
    "Show, Don't Tell : décrire l action plutôt que l émotion.",
    "Séquences de 15-20s max.",
    "Phrase 1 : contradiction choc (ex: Elle a sauvé des milliers de vies. Personne ne connaît son nom.)",
    "Max 18 mots par phrase.",
    "Interdit : né en, décédé en, tout ce qui sonne encyclopédique.",
    "Prompts SDXL avec lighting setup (Rembrandt, Chiaroscuro)."
  ],
  "output_format": {
    "sequence_id": "int",
    "narration": "string (inclure [PAUSE_1S])",
    "emotion_tag": "tension | triomphe | deuil | révélation",
    "visual_prompt": "string (SDXL + IP-Adapter reference)",
    "transition_type": "zoom_in | pan_left | glitch | dissolve | cut"
  }
}
```

### Hook des 5 premières secondes

Ne pas laisser Gemini inventer le hook. Utiliser des templates éprouvés :

```python
HOOK_TEMPLATES = [
    "Elle a {ACTION}. Vous n'avez jamais entendu son nom.",
    "En {ANNÉE}, une femme a {CHANGEMENT}. L'histoire a retenu le nom de son collègue.",
    "On lui a volé {CHOSE}. Elle a quand même {RÉUSSITE}.",
    "Tout le monde connaît {NOM_CÉLÈBRE}. Personne ne sait que c'est {SUJET} qui a tout rendu possible.",
    "Elle avait {ÂGE} ans quand {ÉVÉNEMENT}. On ne lui a jamais pardonné.",
]
```

---

## Points non résolus (à critiquer)

1. Cohérence IP-Adapter sur personnages quasi sans portraits historiques connus
2. Gestion du queue ComfyUI sous charge (plusieurs images en parallèle = OOM VRAM)
3. Format optimal : 8-12 min (algo watch-time) vs Shorts (acquisition) ?
4. Stratégie de publication : 1 longue/semaine + 3 Shorts/semaine ?
5. Fact-checking automatique : jusqu'où faire confiance à Gemini pour valider Gemini ?
