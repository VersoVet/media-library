# media-library - Guide de Développement Forge

> **FICHIER GÉNÉRÉ PAR FORGE - NE JAMAIS MODIFIER**
> En cas de modification, régénérer avec: `forge regenerate-claude media-library`
> Ou via API: POST /api/skills/media-library/regenerate-claude

---

## Écosystème Onyx Forge

### Architecture Globale
```
OnyxDendrite (10.0.0.13)     OnyxSoma (10.0.0.44)
├── Forge (4080)             ├── Core (8050)
│   └── Dev, Validate,       │   └── Registry, Vault
│       Review, Deploy       │
├── LLM Router (8055)        ├── Skills (8xxx)
│   └── Groq, SambaNova,     │   └── APIs déployées
│       Gemini, Codex        │
└── Skills Dev               └── Redis, PostgreSQL
    └── /home/onyx/projects/skills/
```

### Cycle de Vie d'un Skill
```
INTENT → PLAN → INIT → DEV → VALIDATE → REVIEW → DEPLOY
```

### Services Forge (APIs HTTP sur 10.0.0.13:4080)
| Service | Endpoint | Description |
|---------|----------|-------------|
| **Validation** | POST `/api/validate/{skill}` | 18 phases de validation, rapport structuré |
| **Revue** | POST `/api/review/{skill}` | Revue multi-LLM (Groq+SambaNova+Gemini) |
| **Déploiement** | POST `/api/deploy/{skill}` | Déploiement complet (git, SSH, systemd) |

---

## ⚠️ VALIDATION - À LIRE EN PREMIER!

**IMPORTANT**: Votre code sera automatiquement validé par `curl -X POST http://10.0.0.13:4080/api/validate/media-library`

Le validator va checker **18 phases**. Lisez cette section pour éviter les erreurs.

### Phase 1: Structure (Fichiers Obligatoires)
❌ **ERREUR si**:
- `CLAUDE.md` manquant (auto-généré, ne pas supprimer)
- `API.md` manquant (documenter les endpoints)
- `manifest.json` manquant ou invalide
- `src/main.py` manquant (point d'entrée FastAPI)
- `.gitignore` manquant (sécurité)

✅ **À faire**:
```
media-library/
├── CLAUDE.md              # Auto-généré - NE PAS MODIFIER
├── API.md                 # ← À CRÉER: documenter endpoints
├── ARCHITECTURE.md        # ← À CRÉER: structure du code
├── TODO.md                # ← À CRÉER: tâches en cours
├── manifest.json          # Config (auto-généré)
├── .gitignore             # ← À CRÉER: patterns à ignorer
└── src/main.py            # Point d'entrée
```

### Phase 3: Manifest.json - Champs Obligatoires
❌ **ERREUR si**:
- `core.name` manquant
- `core.type` invalide (doit être: python, node, docker, script, custom)
- `core.description` manquant
- `core.brain_area` invalide
- `core.routing.port` en dehors de 8000-9999
- `forge.type` ≠ `core.type` (DOIT matcher!)
- `heart.deployment.target_host` invalide

✅ **Exemple correct**:
```json
{
  "core": {
    "name": "media-library",
    "type": "python",
    "description": "Description courte du skill",
    "brain_area": "prefrontal",
    "routing": {
      "port": 8202
    }
  },
  "forge": {
    "type": "python"
  },
  "heart": {
    "deployment": {
      "target_host": "10.0.0.21"
    }
  }
}
```

### Phase 7: Git & .gitignore
❌ **ERREUR si**:
- `.gitignore` manquant
- `.gitignore` n'inclut pas: `*.pyc`, `__pycache__`, `.env`, `*.key`, `secrets*`
- Remote `origin` non configuré
- Branche `dev` non créée
- Credentials/tokens dans le code

### Phase 15: Taille Fichiers (MAX 300 lignes)
❌ **ERREUR si**:
- `src/main.py` > 300 lignes
- `src/modules/{module}/service.py` > 300 lignes
- `src/modules/{module}/routes.py` > 300 lignes

✅ **À faire**:
- Chaque module < 300 lignes
- Split si nécessaire en `service.py`, `routes.py`, `utils.py`

### Phase 16: Type Checking (mypy - ZÉRO ERREUR)
❌ **ERREUR si**:
- Paramètres sans type annotation
- Retours sans type annotation
- Types incomplets/incorrects

✅ **Exemple correct**:
```python
async def validate(skill_name: str, timeout: float = 30.0) -> dict:
    """Valide la structure d'un skill."""
    return {"valid": True}

# INCORRECT ❌
async def validate(skill_name, timeout=30):
    return {"valid": True}
```

### Phase 18: Docstrings (Google convention - 80%+ coverage)
❌ **ERREUR si**:
- Fonctions publiques sans docstring
- Docstring sans description
- Pas de Args/Returns
- Convention non Google

✅ **Exemple correct**:
```python
def deploy(skill_name: str, target: str) -> bool:
    """Déploie un skill sur un host.
    
    Args:
        skill_name: Nom du skill (kebab-case)
        target: Host cible (IP ou hostname)
        
    Returns:
        True si succès, False sinon
        
    Raises:
        DeploymentError: Si host inaccessible
    """
    pass
```

---

## Architecture Modulaire OBLIGATOIRE

### Structure Standard
```
media-library/
├── manifest.json           # Config (core/heart/forge)
├── requirements.txt        # Dépendances Python
├── CLAUDE.md               # CE FICHIER (NE PAS MODIFIER)
├── ARCHITECTURE.md         # Structure et composants
├── API.md                  # Documentation endpoints
├── TODO.md                 # Tâches en cours
├── .gitignore              # Sécurité
│
├── src/                    # CODE SOURCE
│   ├── __init__.py
│   ├── main.py             # Point d'entrée FastAPI
│   ├── models.py           # Modèles Pydantic
│   │
│   └── modules/            # MODULES FONCTIONNELS
│       ├── __init__.py
│       ├── {module_a}/     # Un module par fonctionnalité
│       │   ├── __init__.py
│       │   ├── service.py  # Logique métier
│       │   ├── routes.py   # Routes FastAPI (optionnel)
│       │   └── tests/      # Tests du module
│       │       └── test_{module_a}.py
│       │
│       └── {module_b}/
│           └── ...
│
└── tests/                  # Tests d'intégration
    └── test_integration.py
```

### Règles Modules
1. **Un module = une responsabilité**
2. **Chaque module a ses propres tests** dans `modules/{nom}/tests/`
3. **Interface claire**: fonctions publiques documentées avec types
4. **Pas de dépendances circulaires** entre modules

### Exemple Module
```python
# src/modules/processor/service.py
"""Module de traitement des données."""

from pydantic import BaseModel

class ProcessRequest(BaseModel):
    data: str
    options: dict = {}

class ProcessResult(BaseModel):
    success: bool
    output: str
    duration_ms: float

async def process(request: ProcessRequest) -> ProcessResult:
    """
    Traite les données selon les options.

    Args:
        request: Données à traiter avec options

    Returns:
        ProcessResult avec le résultat du traitement
    """
    # Implémentation KISS
    ...
```

---

## Principe KISS (Keep It Simple, Stupid)

### À FAIRE
- Code simple et lisible
- Fonctions courtes (<50 lignes)
- Noms explicites
- Un fichier = une responsabilité
- Tests pour chaque module

### À ÉVITER
- Classes avec une seule méthode → utiliser une fonction
- Abstractions pour un seul cas → code direct
- Factory/Builder pour 2-3 objets simples
- Fichiers >300 lignes sans raison
- Configuration excessive

### Règle d'Or
> "200 lignes de code clair > 10 fichiers de 20 lignes"

---

## Réutilisation des Skills Existants

### AVANT de coder une fonctionnalité
1. **Consulter les skills existants** via API ou fichiers
2. **Lire leurs API.md** pour connaître les endpoints disponibles
3. **Utiliser leurs endpoints** plutôt que recoder

### Comment trouver les skills
```bash
# Liste des skills déployés
curl http://10.0.0.44:8050/skills | jq '.skills[].name'

# API d'un skill spécifique
cat /home/onyx/projects/skills/{skill}/API.md

# Ou via Core
curl http://10.0.0.44:8050/skills/{name}/endpoints
```

### Exemple: Utiliser email-notification
```python
import httpx

async def send_notification(subject: str, body: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://10.0.0.44:8054/api/send",
            json={"subject": subject, "body": body},
            timeout=30.0
        )
        return response.json()
```

---

### Autres Phases Critiques

| Phase | À Checker | ✅ Correct | ❌ Erreur |
|-------|-----------|-----------|----------|
| **5. Run mode** | service, gui, oneshot | manifest.json valide | Mode invalide |
| **6. Signaux Redis** | Events/status dans manifest | Champs optionnels | Référence invalide |
| **8. Deploy target** | Host dans inventory | 10.0.0.13, 10.0.0.44 | Host n'existe pas |
| **9. Dépendances** | Imports valides | `from src.config import ...` | Import relatif |
| **10. Dashboard** | Config optionnelle | Présent ou absent | Format invalide |
| **11. SDK Redis** | OnyxClient importé | `from onyx_sdk import ...` | Manquant (warning) |
| **12. Format manifest** | JSON valide | Indentation 2 espaces | JSON malformé |
| **13. Cron tasks** | Endpoints /cron | Valides si présents | Invalides |
| **14. Markdown docs** | ARCHITECTURE.md structuré | Headings, listes | Format invalide |

---

## Tâches Cron (Configuration Optionnelle)

Si votre skill doit effectuer des opérations automatisées (monitoring, cleanup, rapports), définissez-les dans `cron.json`.

### Configuration via cron.json

**Fichier**: `cron.json` (optionnel - ignoré si absent)

**Trois types de commandes**:

1. **HTTP Endpoint** - Appelle un endpoint de votre skill
   ```json
   {
     "type": "endpoint",
     "endpoint": "/health",
     "method": "GET"
   }
   ```

2. **Script Python** - Exécute un script dans votre répertoire skill
   ```json
   {
     "type": "script",
     "script": "scripts/backup.py"
   }
   ```

3. **Commande Shell** - Exécute une commande bash
   ```json
   {
     "type": "command",
     "command": "curl http://metrics/report"
   }
   ```

### Exemple complet

```json
{
  "tasks": [
    {
      "id": "health-check",
      "name": "Hourly Health Check",
      "description": "Verify skill health",
      "schedule": "0 * * * *",
      "command": {
        "type": "endpoint",
        "endpoint": "/health",
        "method": "GET"
      },
      "timeout_seconds": 60,
      "enabled": true,
      "notify_on_failure": true
    }
  ]
}
```

### Validation & Déploiement

- **Phase 13 (Validation)**: Valide syntaxe et structure de `cron.json`
- **Optionnel**: Pas d'erreur si manquant; validator suggère au développeur
- **Déploiement**: Installe les tâches cron sur la machine cible
- **Cleanup**: Supprime les anciennes tâches avant d'installer les nouvelles

Voir `cron.json.example` pour un template complet avec tous les champs.

---

## Fichiers de Documentation

| Fichier | Contenu | Màj quand | Vérifié par |
|---------|---------|-----------|------------|
| **TODO.md** | Tâches, bugs, idées | Début/fin de tâche | Phase 2 (freshness) |
| **ARCHITECTURE.md** | Structure, modules, décisions | Ajout/modif module | Phase 2 (freshness) |
| **API.md** | Endpoints avec exemples curl | Ajout/modif endpoint | Phase 14 (markdown) |
| **CLAUDE.md** | CE FICHIER | JAMAIS (auto-généré) | Phase 1 (structure) |

---

## Configuration Skill

| Champ | Valeur |
|-------|--------|
| **Nom** | media-library |
| **Type** | python |
| **Port** | 8202 |
| **Brain Area** | bibliotheca |
| **Target** | 10.0.0.21 |

---

## Développement Python Optimisé

### Environnement
```bash
# TOUJOURS utiliser le venv global (NE PAS créer de .venv local)
source /opt/onyx/venv/bin/activate

# Vérifier l'activation
which python  # Doit afficher /opt/onyx/venv/bin/python
```

### Linting avec Ruff (OBLIGATOIRE avant commit)
```bash
# Vérifier le code
ruff check src/

# Corriger automatiquement
ruff check src/ --fix

# Formatter le code
ruff format src/
```

### Règles Ruff appliquées
- **E**: Erreurs pycodestyle
- **F**: Erreurs pyflakes (variables inutilisées, imports)
- **W**: Warnings pycodestyle
- **I**: Tri des imports (isort)
- **UP**: Modernisation Python 3.12+
- **B**: Bugs courants (flake8-bugbear)
- **D**: Docstrings obligatoires (Google convention)

### Docstrings OBLIGATOIRES (convention Google)

Chaque fonction, classe et méthode publique DOIT avoir un docstring.
Couverture minimum: 30% (erreur bloquante), objectif: 60%+.

```python
def deploy_skill(name: str, target: str, version: str = "patch") -> DeployResult:
    """Deploy a skill to the target host.

    Args:
        name: Skill name (kebab-case).
        target: Target host IP or hostname.
        version: Version bump type (patch/minor/major).

    Returns:
        DeployResult with status and deployment details.

    Raises:
        DeploymentError: If the target is unreachable.
    """
```

Règles:
- Première ligne: description courte, impérative, terminée par un point.
- Args/Returns/Raises: seulement si pertinent (pas pour les getters simples).
- Fonctions privées (`_xxx`): docstring recommandé mais non obligatoire.

### Bonnes pratiques Python (Validées par Phases 16-18)

#### ✅ Types Explicites (Phase 16: mypy)
```python
# CORRECT - Tous les paramètres et retours typés
async def process(data: str, timeout: float = 30.0) -> dict:
    """Traite les données avec timeout."""
    return {"success": True}

# INCORRECT ❌ - mypy va échouer
async def process(data, timeout=30):
    return {"success": True}
```

#### ✅ Imports Absolus (Phase 7: Git)
```python
# CORRECT - Imports absolus
from src.config import CONFIG
from src.modules.skills import get_skills

# INCORRECT ❌ - Imports relatifs
from config import CONFIG
from .modules.skills import get_skills
```

#### ✅ HTTP Async avec httpx
```python
# CORRECT - httpx async (recommandé)
import httpx

async with httpx.AsyncClient() as client:
    response = await client.get(url, timeout=30.0)
    data = response.json()

# INCORRECT ❌ - requests (bloquant, pas async)
import requests
response = requests.get(url)

# INCORRECT ❌ - aiohttp (moins standard)
import aiohttp
async with aiohttp.ClientSession() as session:
    response = await session.get(url)
```

#### ✅ Pydantic Models
```python
# CORRECT - Validation avec Pydantic
from pydantic import BaseModel, Field

class Request(BaseModel):
    data: str
    options: dict = Field(default_factory=dict)
    timeout: float = 30.0

# INCORRECT ❌ - dataclasses (pas de validation)
from dataclasses import dataclass

@dataclass
class Request:
    data: str
    options: dict = None
```

#### ✅ Docstrings Google Convention (Phase 18)
```python
# CORRECT - Google style
def deploy(skill_name: str, target: str = "10.0.0.13") -> bool:
    """Déploie un skill sur un host cible.
    
    Coordonne git push, SSH, systemd restart.
    
    Args:
        skill_name: Nom du skill (kebab-case)
        target: Host cible (défaut: 10.0.0.13)
        
    Returns:
        True si succès, False sinon
        
    Raises:
        DeploymentError: Si host inaccessible
    """
    pass

# INCORRECT ❌ - Pas de docstring ou mal formattée
def deploy(skill_name, target="10.0.0.13"):
    # Implémentation sans docstring
    pass
```

#### ✅ Pas de Credentials en Dur (Phase 7: Security)
```python
# CORRECT - Vault
async def get_api_key() -> str:
    async with httpx.AsyncClient() as client:
        r = await client.get("http://10.0.0.44:8050/vault/api_key")
        return r.json()["value"]

# INCORRECT ❌ - Hardcoded
API_KEY = "sk-1234567890abcdef"
SECRET = "my-secret-password"
```

---

## Tests

### Structure Tests
```
tests/
├── test_integration.py     # Tests bout-en-bout
└── conftest.py             # Fixtures pytest

src/modules/{module}/tests/
└── test_{module}.py        # Tests unitaires du module
```

### Lancement
```bash
# Tous les tests (mode rapide)
pytest tests/ -x -q

# Un module spécifique
pytest src/modules/processor/tests/

# Avec couverture
pytest --cov=src --cov-report=term-missing

# Tests parallèles (si pytest-xdist installé)
pytest -n auto
```

---

## Sécurité

### Credentials via Vault (OBLIGATOIRE)
```python
import httpx

async def get_secret(key: str) -> str:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"http://10.0.0.44:8050/vault/{key}")
        return r.json()["value"]

# Usage
api_key = await get_secret("mon_api_key")
```

### Jamais en dur
```python
# INTERDIT
API_KEY = "sk-xxx..."

# CORRECT
API_KEY = await get_secret("api_key")
```

---

## Workflow Session

### Au démarrage
1. Lire `/opt/onyx/forge/CLAUDE.md` (règles Forge globales)
2. Lire ce fichier (CLAUDE.md du skill) → **Sections "VALIDATION" critiques!**
3. Lire `TODO.md` (tâches en cours)
4. Lire `ARCHITECTURE.md` (structure actuelle)
5. Lire `API.md` (endpoints existants)
6. Lire `manifest.json` (configuration)

### Développement
1. Identifier la tâche dans TODO.md
2. Créer/modifier le module approprié (< 300 lignes)
3. Ajouter types explicites à toutes les fonctions
4. Écrire docstrings (Google convention)
5. Écrire les tests du module
6. Mettre à jour ARCHITECTURE.md et API.md
7. Ruff check/fix avant commit

### ⚠️ AVANT CHAQUE COMMIT
```bash
# 1. Linting (OBLIGATOIRE)
ruff check src/ --fix
ruff format src/

# 2. Type checking
mypy src/ --strict

# 3. Tests
pytest tests/ -x -q

# 4. VALIDATION (18 phases)
curl -X POST http://10.0.0.13:4080/api/validate/media-library | jq .

# Si validation échoue: affiche les erreurs structurées
# Lisez bien les "correction.action" et "correction.notes"
```

---

## Checklist Pré-Commit (Copiez-collez)

```
📋 AVANT de committer:

Infrastructure:
☐ CLAUDE.md présent (ne pas modifier)
☐ API.md documenterait (endpoints + exemples)
☐ ARCHITECTURE.md à jour
☐ TODO.md reflète l'état du code
☐ .gitignore contient: *.pyc, __pycache__, .env, *.key

Code:
☐ Tous les paramètres ont un type (Phase 16: mypy)
☐ Tous les retours ont un type
☐ Tous les publics ont un docstring (Phase 18)
☐ Docstrings en Google convention
☐ Pas de credentials en dur (Phase 7: Security)
☐ Imports absolus (from src.xxx import)
☐ Chaque module < 300 lignes (Phase 15)
☐ httpx async pour HTTP (pas requests)
☐ Pydantic pour validations

Tests:
☐ pytest passe sans erreur
☐ Tous les modules ont des tests

Validation:
☐ ruff check src/ --fix passe
☐ mypy src/ passe (zéro erreur)
☐ curl -X POST http://10.0.0.13:4080/api/validate/media-library = valid: true

Git:
☐ git status propre (commits fait)
☐ Branch est dev (pas main)
☐ Commit messages clairs
```

---

## Références

| Doc | Usage |
|-----|-------|
| `/opt/onyx/forge/CLAUDE.md` | Règles Forge complètes |
| `http://10.0.0.44:8050/skills` | Skills déployés |
| `http://10.0.0.44:8050/vault/{key}` | Secrets |
