# logs — Monitoring & Debugging

Logs structurés via `structlog`. Un fichier par run, rotation automatique.

## Structure des logs

```
/logs/
  pipeline_2026-03-29_ada-lovelace.json   ← log complet d'un run
  pipeline_2026-03-28_rosa-parks.json
  errors.log                               ← erreurs critiques uniquement
```

## Format JSON (structlog)

```json
{
  "timestamp": "2026-03-29T10:00:00Z",
  "slug": "ada-lovelace",
  "stage": "02-scripts",
  "event": "script_generated",
  "confidence_score": 8,
  "duration_sec": 12.4,
  "llm_source": "gemini",
  "level": "info"
}
```

## Niveaux de log

| Niveau | Usage |
|---|---|
| `info` | Étape terminée avec succès |
| `warning` | Fallback Ollama activé, score < 8, fait douteux |
| `error` | Exception, timeout, crash API |
| `critical` | Échec irrémédiable → notification Telegram immédiate |

## Alertes Telegram automatiques

Tout log `critical` déclenche une notification Telegram :
```
🚨 ERREUR CRITIQUE
Slug : ada-lovelace
Stage : 03-assets (ComfyUI)
Erreur : CUDA out of memory
Temps écoulé : 8 min

Action requise : vérifier VRAM et relancer manuellement.
```
