# media-library - Diagramme Fonctionnel

> Genere par Forge. Regenerer: POST /api/skills/media-library/generate-diagram

## Diagramme

```mermaid
graph TD
    %% Subgraph Modules internes
    subgraph "Modules internes"
        A[FastAPI] 
        B[Catalog] 
        C[Dropbox] 
        D[Tagger] 
        E[Search] 
        F[Sources] 
        G[Scanner] 
        H[(SQLite DB)]
    end

    %% Subgraph Endpoints HTTP
    subgraph "Endpoints HTTP"
        EP1[/health] 
        EP2[/info] 
        EP3[/api/upload] 
        EP4[/api/media/{id}] 
        EP5[/api/media/{id}/thumb] 
        EP6[/api/media/{id}/suggest] 
        EP7[/api/search] 
        EP8[/api/scan] 
    end

    %% Subgraph Dependances externes
    subgraph "Dependances externes"
        EX1[Dropbox API] 
        EX2[Groq LLM] 
        EX3[ffmpeg/Pillow] 
        EX4[SQLite file] 
    end

    %% Interactions internes
    A --> B : "gère"
    A --> C : "utilise"
    A --> D : "utilise"
    A --> E : "utilise"
    A --> F : "gère"
    A --> G : "gère"
    A --> H : "ORM"

    B --> H : "CRUD"
    B --> C : "stocke"
    B --> D : "tags AI"
    B --> EX3 : "miniatures"

    D --> EX2 : "LLM vision"

    E --> H : "recherche"

    G --> F : "scanne"
    G --> C : "télécharge"

    %% Endpoints vers modules
    EP1 --> A : "vérif"
    EP2 --> A : "info"
    EP3 --> B : "upload"
    EP4 --> B : "détails"
    EP5 --> B : "miniature"
    EP6 --> D : "suggestion"
    EP7 --> E : "requête"
    EP8 --> G : "déclenche"

    %% Modules vers dépendances externes
    C --> EX1 : "API"
    H --> EX4 : "fichier"

    %% Styles
    classDef endpoint fill:#4CAF50,stroke:#333,color:#fff;
    classDef module fill:#2196F3,stroke:#333,color:#fff;
    classDef external fill:#FF9800,stroke:#333,color:#fff;
```
