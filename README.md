# pibooth-background-changer

Plugin pour [pibooth](https://github.com/pibooth/pibooth) permettant de supprimer automatiquement le fond des photos et de le remplacer par un fond personnalisé.

![Demo](docs/demo.gif)

## Fonctionnalités

- Suppression automatique du fond par IA (utilise [rembg](https://github.com/danielgatis/rembg))
- Choix parmi plusieurs fonds personnalisés
- Navigation entre les fonds avec les boutons tactiles ou les flèches gauche/droite
- Option "Sans fond" pour garder la photo originale
- Activation/désactivation à la volée
- Bandeau d'information avec miniature du fond sélectionné
- Auto-masquage du bandeau après quelques secondes
- **Détection automatique du GPU** (NVIDIA CUDA, Intel OpenVINO, AMD ROCm, Apple CoreML)
- **Sélection automatique du modèle** optimal selon la plateforme

## Installation

### Prérequis

- Python 3.7+
- pibooth 2.0+

### Installation standard

```bash
pip install pibooth-background-changer
```

### Installation avec support GPU

```bash
# NVIDIA GPU (CUDA)
pip install pibooth-background-changer[gpu-nvidia]

# Intel GPU (OpenVINO)
pip install pibooth-background-changer[gpu-intel]

# AMD GPU (DirectML - Windows)
pip install pibooth-background-changer[gpu-amd-windows]

# AMD GPU (ROCm - Linux)
pip install pibooth-background-changer[gpu-amd-linux]

# Apple Silicon (CoreML)
pip install pibooth-background-changer[gpu-apple]
```

### Installation depuis les sources

```bash
git clone https://github.com/ceeeeb/pibooth-background-changer.git
cd pibooth-background-changer
pip install -e .
```

## Configuration

Ajoutez vos images de fond dans le dossier configuré (par défaut `~/.config/pibooth/backgrounds/`).

### Options de configuration

Dans `~/.config/pibooth/pibooth.cfg` :

```ini
[BACKGROUND_CHANGER]
# Chemin vers le dossier contenant les images de fond
backgrounds_path = ~/.config/pibooth/backgrounds

# Activer le remplacement de fond au démarrage
enabled = True

# Modèle IA pour la suppression de fond
# Options: auto, silueta, u2netp, u2net, u2net_human_seg, isnet-general-use
# "auto" sélectionne automatiquement le meilleur modèle pour votre plateforme
model = auto

# Traiter les captures individuelles (True) ou seulement l'image finale (False)
process_captures = True
```

### Modèles disponibles

| Modèle | Taille | Vitesse | Qualité | Recommandé pour |
|--------|--------|---------|---------|-----------------|
| `silueta` | 4 MB | Très rapide | Bonne | Raspberry Pi |
| `u2netp` | 4 MB | Rapide | Bonne | CPU lent |
| `u2net_human_seg` | 176 MB | Moyen | Très bonne | Portraits |
| `u2net` | 176 MB | Moyen | Excellente | Desktop |
| `isnet-general-use` | 178 MB | Lent | Excellente | GPU puissant |

### Détection automatique

Avec `model = auto`, le plugin sélectionne automatiquement :
- **Raspberry Pi** : `silueta` (rapide, léger)
- **Desktop/GPU** : `isnet-general-use` (meilleure qualité)

### Accélération GPU supportée

| GPU | Provider ONNX | Installation |
|-----|---------------|--------------|
| NVIDIA | CUDA / TensorRT | `onnxruntime-gpu` |
| Intel | OpenVINO | `onnxruntime-openvino` |
| AMD (Windows) | DirectML | `onnxruntime-directml` |
| AMD (Linux) | ROCm | `onnxruntime-rocm` |
| Apple Silicon | CoreML | `onnxruntime-coreml` |

## Raspberry Pi

### Limitations du VideoCore VI

Le GPU VideoCore VI du Raspberry Pi 4/5 **n'est pas directement supporté** par ONNX Runtime. Le plugin utilise donc le CPU avec un modèle optimisé (`silueta`).

### Optimisations pour Raspberry Pi

1. **Modèle léger** : Le mode `auto` sélectionne `silueta` (~4 MB)
2. **Résolution réduite** : Traitement à 640x480 par défaut
3. **RAM** : Minimum 2 GB recommandé

### Configuration recommandée pour Raspberry Pi

```ini
[CAMERA]
resolution = (640, 480)

[BACKGROUND_CHANGER]
model = silueta
enabled = True
```

### Temps de traitement estimés (Raspberry Pi 4)

| Modèle | Résolution | Temps |
|--------|------------|-------|
| silueta | 640x480 | ~3-5 sec |
| u2netp | 640x480 | ~5-8 sec |
| u2net | 640x480 | ~15-20 sec |

## Utilisation

1. Lancez pibooth normalement
2. En mode attente, utilisez les **boutons tactiles** ou les **flèches GAUCHE/DROITE** pour changer de fond
3. Le bandeau affiche le fond sélectionné avec une miniature
4. Le fond sera automatiquement appliqué aux photos prises

### Contrôles

- **Bouton `<`** ou **Flèche GAUCHE** : Fond précédent
- **Bouton `>`** ou **Flèche DROITE** : Fond suivant
- **"Sans fond"** : Option par défaut pour garder la photo originale

## Formats d'images supportés

- JPEG (.jpg, .jpeg)
- PNG (.png)
- BMP (.bmp)
- GIF (.gif)
- WebP (.webp)

## Dépannage

### Le plugin ne se charge pas

Vérifiez que rembg est installé :
```bash
pip install rembg
```

### Traitement trop lent

1. Utilisez le modèle `silueta` :
```ini
model = silueta
```

2. Réduisez la résolution de la caméra :
```ini
[CAMERA]
resolution = (640, 480)
```

3. Installez le support GPU si disponible

### Erreur de mémoire sur Raspberry Pi

```ini
model = silueta
```

### Vérifier l'accélération GPU

Les logs affichent le provider utilisé :
```
Available ONNX providers: ['CUDAExecutionProvider', 'CPUExecutionProvider']
Using CUDA (NVIDIA GPU) acceleration
```

## Licence

MIT License

## Crédits

- [pibooth](https://github.com/pibooth/pibooth) - Framework photobooth
- [rembg](https://github.com/danielgatis/rembg) - Suppression de fond par IA
- [ONNX Runtime](https://onnxruntime.ai/) - Inférence optimisée
