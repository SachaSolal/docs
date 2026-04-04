# Prompt — Critique Architecture V3

---

Tu es un expert senior en pipelines d'automatisation vidéo full-AI et en stratégie de contenu YouTube.

## Contexte

Je développe une chaîne YouTube 100% automatisée sur les biographies de femmes historiques oubliées.
Objectif : 1 vidéo par semaine, zéro coût API, Python-driven, orchestré via n8n self-hosted.

## Architecture V3 — Décisions actées

### Stack

- **Orchestration** : n8n self-hosted (cron trigger, nodes HTTP, Execute Command)
- **LLM** : Gemini API free tier (primaire) + Ollama Llama3 local (fallback si rate limit)
- **Retry** : tenacity avec `retry_if_exception_type(ResourceExhausted)` uniquement — pas de retry sur erreurs 400
- **Cache** : fichier JSON local par sujet pour éviter toute re-génération Gemini
- **Voix** : F5-TTS ou Kokoro-TTS (clonage vocal de ma propre voix)
- **Sound design** : room tone + SFX contextuels (vent, parchemin, feu) sous la voix off
- **Images** : SDXL via ComfyUI API locale
- **Cohérence visuelle** : IP-Adapter (weight 0.6) + ControlNet OpenPose + Style LoRA
- **Lighting SDXL** : Rembrandt / Chiaroscuro dans tous les prompts
- **Montage** : FFmpeg via subprocess Python (remplace MoviePy)
- **Ken Burns** : zoompan FFmpeg avec point focal aléatoire + shake humanisé (sin(random()))
- **Cuts** : calés sur les silences détectés par librosa
- **Transitions** : déterminées par emotion_tag (glitch=tension, dissolve=deuil, zoom_in=triomphe)
- **Sous-titres** : faster-whisper + animation mot par mot (Pillow + numpy)
- **Upload** : YouTube Data API v3 — upload puis attente 45s puis update métadonnées (2 appels séparés)
- **Thumbnail** : SDXL (visage du personnage + texte choc)
- **Hook** : templates pré-écrits (Gemini choisit parmi 5, ne l'invente pas)
- **Monitoring** : structlog

### Format de sortie Gemini (JSON par séquence)

```
sequence_id | narration (avec [PAUSE_1S]) | emotion_tag | visual_prompt SDXL | transition_type
```

### Génération script en 2 passes

1. Passe structure : plan en 8 tableaux de 20s
2. Passe narrative : rédaction avec contraintes strictes (max 18 mots/phrase, pas de ton encyclopédique, accroche contradiction)

## Questions pour ta critique

### Technique
1. Le fallback Ollama génère un script de qualité inférieure à Gemini. Comment détecter automatiquement la dégradation de qualité et décider si la vidéo est publiable sans review humaine ?
2. IP-Adapter sur un personnage historique avec zéro portrait connu (ex : femme du IIe siècle) — comment gérer la cohérence visuelle sans référence de base ?
3. Le queue ComfyUI : si 8 images SDXL sont générées séquentiellement, le temps de rendu peut dépasser 2h sur GPU grand public. Quelle stratégie pour paralléliser sans OOM ?
4. Le fait-checking est fait par Gemini sur des données scrapées, puis le script est aussi généré par Gemini. C'est le même modèle qui valide ses propres données. Comment briser cette circularité ?

### Stratégie contenu
5. Format optimal : une longue vidéo (8-12 min) par semaine ou 1 longue + 3 Shorts dérivés automatiquement ? Lequel maximise la croissance en phase de démarrage (0-1000 subs) ?
6. La stratégie "zéro intervention humaine" est-elle tenable au-delà de 50 vidéos publiées, ou l'algo YouTube finit-il par dégrader les vidéos full-auto sur la durée ?

### Architecture globale
7. n8n est l'orchestrateur visuel choisi. Y a-t-il un point de friction spécifique entre n8n et les scripts Python locaux (ComfyUI, FFmpeg, faster-whisper) que je n'anticipe pas ?
8. Identifie le maillon le plus fragile de toute la chaîne et propose une alternative concrète.

## Ce que j'attends

- Réponses directes et techniques (pas de bla-bla)
- Du code Python ou des commandes concrètes quand c'est pertinent
- Un classement des 3 risques majeurs par ordre de priorité
- Une alternative d'architecture complète si tu penses que l'approche est fondamentalement limitée
