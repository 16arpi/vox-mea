# Synthèse vocale personnelle

_Vox mea_ est un programme de synthèse vocale par concaténation de diphones prenant appuie sur ma propre voix. Projet réalisé dans le cadre du cours de Synthèse de la parole (Cédric Gendrot, M1 TAL, Sorbonne Nouvelle).

Développé sous python v3.11

## Installation

Installer les dépendances à l'aide de :

```bash
$ pip install -r requirements.txt
```

Ou bien :

```bash
$ pip install praat-parselmouth praat-textgrids requests TTS
```

## Utilisation

> Attention : ce programme nécessite une connexion internet

Pour lancer le programme, executer la commande suivante :

```bash
python -m synthese "C'est une affaire intéressante, qu'en pensez-vous ?"
```

Les paramètres disponibles sont :

* `-h`, `--help` : Montrer le message d'aide
* `-o OUTPUT`, `--output OUTPUT` : Spécifier le nom du fichier audio généré
* `-p`, `--never-use-phonemes` : Evite que le programme utilise des phonèmes quand des diphones sont indisponibles.
* `-l`, `--legacy-phonetizer` : Utilise l'ancien phonetiseur basé sur Espeak (par défaut utilise la synthèse neuronale).
* `-g`, `--gui` : Lance le programme en mode graphique.

## Exemples d'audios

Se trouve dans le dossier `./samples` 5 audios issus de la synthèse des phrases suivantes :

* _C'est une affaire intéressante, quand pensez vous ?_
* _Bonjour, je m'appelle César, j'habite à Paris et j'ai vingt-cinq ans_
* _J'ai conçu cette synthèse vocale à partir de ma propre voix_
* _Tu veux que je te prenne des trucs au franprix ?_
* _Du bristole et de la naphtaline de chez leroi merlin_


## Fonctionnement

### Phonétiseur (label SAMPA, durée, fréquence fondamentale)

Le programme propose deux phonétiseurs différents : `CoquiTTSPhonetizer` ou `PraatPhonetizer`.

Alors que le second est basé sur la méthode présentée en cours (synthétiseur espeak, lecture du textgrid, valeurs de f0/durée aux occurences des phonèmes etc.), le premier est plus complexe car il repose sur une synthèse neuronale préalable.

À partir d'une phrase en français, le processus de phonétisation se découpe en 4 étapes :

1. Nous chargeons le modèle [VITS](https://docs.coqui.ai/en/latest/models/vits.html) de CoquiTTS et nous lui demandons de générer un fichier WAV à partir de la phrase. Ce fichier WAV est placé dans un sous-dossier caché. Un fichier TXT contenant la phrase est aussi créé dans ce sous-dossier.
2. Nous envoyons le fichier WAV et le fichier TXT vers un webservice où est executé le programme [_Munich AUtomatic Segmentation System_](https://www.bas.uni-muenchen.de/Bas/BasMAUS.html). Ce programme prend le fichier WAV et le fichier TXT et renvoie un fichier TextGrid comprenant une segmentation en phonèmes de la phrase.
3. Ensuite, nous explorons les intervalles du TextGrid téléchargé et nous renvoyons, au fur et à mesure, les informations sur ces phonèmes (label SAMPA, durée, f0).
4. Nous supprimons le sous dossier caché qui ne nous sert plus.

L'instance permet de renvoyer une liste de dictionnaires. Chaque dictionnaire comprend trois informations :

* Le label SAMPA
* la durée du phonème
* La fréquence fondamentale

### Synthétiseur

Une fois nos informations phonétiques en poche, la seconde étape consiste, d'une part, à concaténer les diphones puis, d'autre part, à moduler leur durée et leur fréquence fondamentale.

Pour la première partie, nous itérons dans nos informations phonétiques deux par deux. À chaque étape, nous allons chercher dans notre enregistrement de logatomes des diphones associés. Si nous ne trouvons pas le diphone souhaité, nous nous permettons de récupérer deux phonèmes disjoints pour que le programme continue (sauf choix contraire au lancement du programme). On garde, aux côtés de la durée et de la f0, le moment du début et de la fin des deux phonèmes. Nous renvoyons nos informations phonétiques ainsi mises à jour et l'audio des diphones concaténés.

Vient la seconde partie ou nous itérons de phonème en phonème et pour chaque, nous appliquons sur l'audio les transformations liées à la durée et à la fréquence fondamentale (sur le segment d'audio concerné par le phonème). Avec cette étape, nous nous assurons que la f0 et la durée des phonèmes est la même que pour l'audio de la synthèse neuronale.

Nous enregistrons le nouvel audio dans un fichier WAV.
