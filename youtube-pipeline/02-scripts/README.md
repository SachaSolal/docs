# 02-scripts — Génération & Validation des Scripts

Ce module génère le script narratif via Gemini (2 passes),
effectue le fact-checking, attribue un confidence_score,
et route le fichier vers /approved ou /review_needed.

## Flux de traitement

```
[Input]  /knowledge_base/{slug}/*.json
    |
    v
[Passe 1] Structure narrative (8 tableaux de 20s)
    |
    v
[Passe 2] Rédaction + confidence_score
    |
    +-- score >= 8 + 0 fait inventé → /approved/{slug}.json
    +-- score < 8  OU fait douteux  → /review_needed/{slug}.json
                                       + Notification Telegram
```

---

## System Prompt Gemini — Format JSON Narratif

```json
{
  "role": "Directeur de création - Documentaires Premium",
  "style": "Cinématique, sombre, focalisé sur l injustice et la résilience",
  "langue": "Français, registre soutenu sans être académique",
  "instructions": [
    "INTERDIT : adjectifs clichés (incroyable, magnifique, extraordinaire).",
    "INTERDIT : ton encyclopédique (née en, décédée en, elle fut).",
    "OBLIGATOIRE : Show, Don t Tell — décrire l action, pas l émotion.",
    "OBLIGATOIRE : séquences de 15 à 20 secondes maximum.",
    "OBLIGATOIRE : phrase d ouverture = contradiction choc.",
    "OBLIGATOIRE : max 18 mots par phrase.",
    "OBLIGATOIRE : inclure [PAUSE_1S] aux moments dramatiques.",
    "OBLIGATOIRE : générer des prompts SDXL avec lighting setup (Rembrandt, Chiaroscuro)."
  ],
  "output_format": {
    "metadata": {
      "subject": "string — nom complet du personnage",
      "period": "string — époque historique",
      "confidence_score": "int (0-10) — score basé sur : densité des sources vérifiées, absence de contradictions, couverture des faits clés. JAMAIS > 9 si lacunes dans les sources.",
      "confidence_justification": "string — explication du score en 1 phrase",
      "total_sequences": "int"
    },
    "sequences": [
      {
        "sequence_id": "int",
        "narration": "string (inclure [PAUSE_1S] si nécessaire)",
        "emotion_tag": "tension | triomphe | deuil | révélation | colère | espoir",
        "visual_prompt": "string — prompt SDXL détaillé avec style, lighting, composition",
        "transition_type": "zoom_in | pan_left | pan_right | glitch | dissolve | cut_sec",
        "duration_sec": "int (15-20)"
      }
    ],
    "hook_template_used": "string — template de hook sélectionné",
    "youtube_metadata": {
      "title": "string — titre accrocheur (max 60 chars)",
      "description": "string — 150 mots, SEO-friendly",
      "tags": ["string"]
    }
  }
}
```

---

## Prompt de Fact-Checking (externe à Gemini)

Le fact-check compare le script aux sources brutes — Gemini ne s'auto-évalue pas,
il compare objectivement texte vs sources :

```python
FACT_CHECK_PROMPT = """
Compare ce script aux sources historiques fournies.
Pour chaque affirmation factuelle du script, classe-la :

- VERIFIE  : confirmé dans 2+ sources fournies
- PROBABLE : cohérent avec les sources, non confirmé explicitement
- DOUTEUX  : non trouvé dans les sources ou ambigu
- INVENTE  : absent de toutes les sources ou contredit

Sources disponibles :
{sources_brutes}

Script à vérifier :
{script_narratif}

Réponds en JSON :
{
  "faits": [
    {"texte": "...", "statut": "VERIFIE|PROBABLE|DOUTEUX|INVENTE", "source": "url ou null"}
  ],
  "nb_invente": int,
  "nb_douteux": int,
  "verdict": "PUBLIER | REVISION | REJETER"
}

Règles de verdict :
- REJETER  : nb_invente > 0
- REVISION : nb_douteux > 2
- PUBLIER  : nb_invente = 0 ET nb_douteux <= 2
"""
```

---

## Logique de routage Python

```python
import shutil
import json

def route_script(slug: str, script: dict, fact_check: dict) -> str:
    score = script["metadata"]["confidence_score"]
    verdict = fact_check["verdict"]

    if verdict == "REJETER" or score < 6:
        dest = f"02-scripts/review_needed/{slug}.json"
        reason = f"Score={score}, verdict={verdict}, inventés={fact_check['nb_invente']}"
        notify_telegram(f"❌ {slug} rejeté — {reason}")
        return "rejected"

    if verdict == "REVISION" or score < 8:
        dest = f"02-scripts/review_needed/{slug}.json"
        notify_telegram(
            f"⚠️ {slug} à valider\n"
            f"Score: {score}/10\n"
            f"Faits douteux: {fact_check['nb_douteux']}\n"
            f"Répondre: /ok_{slug} ou /reject_{slug}"
        )
        return "review"

    # Score >= 8 ET verdict PUBLIER
    dest = f"02-scripts/approved/{slug}.json"
    return "approved"
```

---

## Note sur le confidence_score

Le score est **indicatif**, pas absolu. Gemini ne peut pas savoir
ce qu'il ignore. Ce score mesure la densité des sources vérifiées,
pas la vérité absolue. Toujours combiné avec le fact-check externe.

Échelle :
- 9-10 : Sources abondantes, faits recoupés, personnage bien documenté
- 7-8  : Sources correctes, quelques lacunes mineures
- 5-6  : Sources limitées, personnage peu documenté → révision conseillée
- < 5  : Sources insuffisantes → rejeter, choisir un autre sujet
