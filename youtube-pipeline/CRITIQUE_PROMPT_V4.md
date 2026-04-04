# Prompt — Critique Architecture V4 (Final)

---

Tu es un expert senior en systèmes d'automatisation vidéo full-AI, DevOps Python et stratégie de contenu YouTube.

## Contexte

Je construis une usine à vidéos YouTube 100% automatisée sur les **biographies de femmes historiques oubliées**.
Objectif : **1 vidéo par semaine**, zéro coût API, orchestré localement.

Le projet est open source et disponible ici :
https://github.com/SachaSolal/docs/tree/claude/youtube-api-features-MR7w0/youtube-pipeline

---

## Architecture V4 — Décisions actées

### Infrastructure

```
Docker Compose (3 services) :
  n8n          → orchestrateur visuel (cerveau)
  video_worker → Python + FFmpeg + FastAPI (muscles)
  comfyui      → SDXL image generation (pinceau)

Communication inter-services :
  - Tâches courtes (<30s) : n8n → Execute Command → script Python
  - Tâches longues (>30s) : n8n → HTTP POST FastAPI → polling GET /status/{job_id}

Volumes partagés Docker :
  /data/knowledge_base/   → sources biographiques par sujet
  /data/inputs/           → JSON déposés par n8n
  /data/exports/          → vidéos MP4 finales
  /data/logs/             → logs structurés (structlog)
```

### State Management

```
SQLite (/config/pipeline.db) — table subjects :
  slug | name | status | confidence_score | llm_source |
  fact_check_verdict | youtube_url | error_message | timestamps

Statuts possibles :
  pending → research → scripting → review | approved →
  assets → editing → uploading → done | rejected | error
```

### Pipeline complet (8 étapes)

```
[1] TRIGGER
    n8n CRON (1x/semaine) → slug + nom du personnage

[2] RECHERCHE MULTI-SOURCES (parallèle)
    Wikipedia API + Semantic Scholar + Tavily (gratuit 1000/mois)
    + Gemini Grounding (Google Search intégré, gratuit)
    + Wikimedia Commons (images domaine public)
    + Gallica BNF (archives françaises)
    → Consolidation Gemini → /knowledge_base/{slug}/*.json

[3] GÉNÉRATION SCRIPT (2 passes Gemini)
    Passe 1 : structure 8 tableaux de 20s (JSON)
    Passe 2 : rédaction narrative (style BBC/Netflix, Morgan Freeman)
    Output JSON par séquence :
      sequence_id | narration [PAUSE_1S] | emotion_tag |
      visual_prompt SDXL | transition_type | duration_sec
    + youtube_metadata (titre, description, tags)
    + hook sélectionné parmi 5 templates pré-écrits

    Fallback : Ollama Llama3 local si Gemini rate limit
    → tenacity retry sur ResourceExhausted uniquement
    → source trackée ("gemini" ou "ollama") dans SQLite

[4] FACT-CHECKING (Gemini compare script vs sources brutes)
    Chaque fait classé : VERIFIE | PROBABLE | DOUTEUX | INVENTE
    Verdict automatique :
      REJETER  → nb_invente > 0
      REVISION → nb_douteux > 2
      PUBLIER  → nb_invente=0 ET nb_douteux<=2

[5] ROUTAGE + VALIDATION HUMAINE (Telegram)
    confidence_score >= 8 + verdict PUBLIER → /02-scripts/approved/
    sinon → /02-scripts/review_needed/ + notification Telegram
    Réponse via webhook : /ok_{slug} ou /reject_{slug}

[6] GÉNÉRATION IMAGES (ComfyUI via FastAPI async)
    Séquence 1 : portrait neutre → image de référence IP-Adapter
    Séquences 2-N : SDXL + IP-Adapter (weight=0.6)
                  + ControlNet OpenPose
                  + Style LoRA (baroque_painting, renaissance)
                  + Lighting Rembrandt/Chiaroscuro dans les prompts
    Fallback images : Wikimedia Commons → Gallica BNF → SDXL

    Timeout n8n : polling /status/{job_id} toutes les 60s, max 20 tentatives (20 min)

[7] AUDIO (F5-TTS ou Kokoro-TTS)
    Clonage vocal sur sample personnel (3-10s)
    [PAUSE_1S] du script → silences réels
    + Room tone + SFX selon emotion_tag (vent, parchemin, feu)
    FFmpeg mix : voix (100%) + sfx (8%)

[8] MONTAGE (FFmpeg via subprocess Python)
    Ken Burns : zoompan FFmpeg, point focal aléatoire, shake humanisé
    Cuts calés sur silences détectés par librosa
    Transitions selon emotion_tag :
      tension=glitch | triomphe=zoom_in | deuil=dissolve |
      révélation=fade_noir | colère=cut_sec | espoir=pan_left
    Sous-titres : faster-whisper + animation mot par mot (Pillow)
    Sous-titres anglais : whisper task="translate" (sans API externe)
    Grain pellicule léger en overlay

[9] VALIDATION THUMBNAIL (Telegram)
    SDXL génère la thumbnail (visage + texte choc)
    Envoi photo Telegram → attente /pub_{slug} ou /regen_{slug}

[10] UPLOAD YOUTUBE
    Upload en "private" → attente 45s → update métadonnées (2 appels séparés)
    Publication à heure variable (9h-11h aléatoire)
    Notification Telegram finale avec lien + stats
```

---

## Décisions techniques spécifiques

**GPU** : n8n et video_worker ne touchent pas le GPU. ComfyUI seul l'utilise.
Les deux services ne tournent JAMAIS en même temps — n8n les séquence.

**Sécurité Docker** : pas de docker.sock monté dans n8n.
video_worker expose une FastAPI (port 5000) pour les jobs longs.

**Monitoring** : structlog JSON, un fichier par run.
Tout log `critical` → notification Telegram immédiate.

**Cache** : scripts déjà générés en JSON → jamais re-générés (SQLite status=done).

**Human-in-the-loop** : 2 points uniquement (fact-check douteux + thumbnail).
Temps humain estimé : 2-5 min par vidéo.

---

## Questions pour ta critique

### Technique
1. Le séquencement GPU (ComfyUI seul utilise le GPU) est-il suffisant pour éviter les OOM, ou faut-il ajouter un mécanisme de réservation explicite (ex: lock fichier, semaphore) ?
2. FastAPI dans le video_worker est synchrone pour les jobs courts. Pour les jobs longs (FFmpeg 10+ min), faut-il passer à `asyncio` + `BackgroundTasks` ou un worker dédié (Celery) est-il justifié pour 1 vidéo/semaine ?
3. Le fallback Ollama génère des scripts de qualité inférieure. Faut-il bloquer l'upload automatique sur les scripts Ollama et forcer une révision humaine systématique ?
4. Whisper `task="translate"` pour les sous-titres anglais : la qualité de traduction est-elle suffisante pour une chaîne professionnelle, ou faut-il prévoir DeepL API dès le départ ?

### Architecture globale
5. La Knowledge Base est un dossier de fichiers JSON plats. À quel volume de sujets (50 ? 200 ? 500 ?) deviendrait-il pertinent de migrer vers une base vectorielle (ChromaDB) pour la recherche sémantique ?
6. n8n est l'unique point d'orchestration. Si n8n crash pendant un run de 47 minutes, l'état SQLite est cohérent mais le run est perdu. Comment gérer la reprise automatique sans complexifier l'architecture ?
7. Le pipeline est prévu pour 1 vidéo/semaine. Quels sont les 3 changements architecturaux minimaux pour passer à 5 vidéos/semaine si la chaîne décolle ?

### Stratégie contenu
8. La stratégie "1 longue vidéo/semaine + sous-titres EN automatiques" est-elle optimale pour la phase 0-1000 abonnés, ou vaut-il mieux commencer par des Shorts (60s) pour l'acquisition initiale ?

---

## Ce que j'attends

- Réponses directes et techniques (pas de bla-bla)
- Code Python ou config concrète quand pertinent
- Classement des 3 risques majeurs par ordre de priorité
- Un point que je n'ai pas anticipé et qui pourrait tout bloquer
