import sys
import shutil
import math
import re
import random
import os
import torch
import requests
import xml.etree.ElementTree as ET
import playsound
import argparse

from parselmouth import Sound, WindowShape, SoundFileFormat
from parselmouth.praat import call
from textgrids import TextGrid
from TTS.api import TTS

SAMPA = re.compile(r'^([a-z]|[A-Z]|[0-9]|~|@)+$')
SAMPA_REPLACEMENTS = {
    "E": "e",
    "e": "E",
    "w": "o"
}

class Phonetizer:
    def __init__(self):
        self.SAMPA = re.compile(r'^([a-z]|[A-Z]|[0-9]|~|@)+$')

    def clean_sampa(self, code: str):
        if '-' in code:
            code = code.replace('-', '')
        if code == '9~':
            code = 'e~'
        if code == '2' or code == 'Y':
            code = '@'
        if code == 'A~' or code == 'E~' or code == 'O~':
            code = code.lower()
        return code

    def phonetic(self, sentence):
        pass

class PraatPhonetizer(Phonetizer):
    def __init__(self):
        super().__init__()

    def phonetic(self, sentence):
        # return phonetic_data, phonetic_sound
        synthese = call("Create SpeechSynthesizer", "French (France)", "Michel")
        call(synthese, "Speech output settings", 44100, 0.01, 1, 1, 175, "Kirshenbaum_espeak")
        grid, sound = call(synthese, "To Sound", sentence, "yes")

        grid_size = call(grid, "Get number of intervals", 4)
        pitchs = sound.to_pitch_ac()

        #
        for i in range(1, grid_size):
            label = call(grid, "Get label of interval", 4, i)

            start = call(grid, "Get start time of interval", 4, i)
            end = call(grid, "Get end time of interval", 4, i)

            moy = (start + end) / 2
            f0 = pitchs.get_value_at_time(moy)
            length = end - start


            # Ajouter des filtre à intervalles inutiles (genre espace, silence etc.)
            label = self.clean_sampa(label)
            if not self.SAMPA.match(label):
                continue


            yield {
                "label": label,
                "length": length,
                "f0": f0 if f0 != "nan" else None
            }

class CoquiTTSPhonetizer(Phonetizer):

    def get_sound_textgrid(self, sentence):
        url_maus_service = "https://clarin.phonetik.uni-muenchen.de/BASWebServices/services/runMAUSBasic"
        # Generation d'un id hash (pour pas écraser le moindre fichier)
        # Création d'un dossier caché ".hash"

        hash = '%032x' % (random.getrandbits(128))
        self.tts_output_dir = '.' + hash
        self.tts_output_wav = self.tts_output_dir + '/output_' + hash + '.wav'
        self.tts_output_txt = self.tts_output_dir + '/output_' + hash + '.txt'
        self.tts_output_tg = self.tts_output_dir + '/output_' + hash + '.TextGrid'
        os.mkdir(self.tts_output_dir)


        # Synthese CoquiTTS > écriture dans un fichier wav
        device = "cuda" if torch.cuda.is_available() else "cpu"

        #tts = TTS("tts_models/multilingual/multi-dataset/your_tts").to(device)
        tts = TTS("tts_models/fr/css10/vits").to(device)
        tts.tts_to_file(sentence, file_path=self.tts_output_wav)

        # Ecriture de la phrase dans un fichier texte
        with open(self.tts_output_txt, 'w') as output_transcript:
            output_transcript.write(sentence)

        # Lancement du webservice MAUS
        with open(self.tts_output_wav, 'rb') as file_wav:
            with open(self.tts_output_txt) as file_txt:
                files = {
                    "SIGNAL": file_wav,
                    "TEXT": file_txt
                }
                data = {
                    "LANGUAGE": "fra-FR",
                    "OUTFORMAT": "TextGrid"
                }
                res = requests.post(
                    url_maus_service,
                    files=files,
                    data=data
                )
                if res.status_code != 200:
                    raise Exception(f"Erreur lors du contact avec webservice MAUS (code {res.status_code})")

        #with open(tts_output_tg, 'w') as file_tg:
        #    file_tg.write(res.text)

        maus_result = ET.fromstring(res.text)

        print("mause result", maus_result)
        mause_link = maus_result[1].text

        print("mause link", mause_link)

        res = requests.get(mause_link)
        if res.status_code != 200:
            raise Exception(f"Erreur lors du téléchargement du TextGrid MAUS (code {res.status_code})")

        with open(self.tts_output_tg, "w") as file_tg:
            file_tg.write(res.text)

        return TextGrid(self.tts_output_tg), Sound(self.tts_output_wav)

    def phonetic(self, sentence):
        tts_grid, tts_sound = self.get_sound_textgrid(sentence)

        pitchs = tts_sound.to_pitch_ac()

        for e in tts_grid["MAU"]:
            label = e.text

            start = e.xmin
            end = e.xmax

            moy = (start + end) / 2

            # Experimental : five f0 steps
            f0_steps = map(lambda x: ((end - start) / 5) * x, range(1, 5))
            f0s = [pitchs.get_value_at_time(start + a) for a in f0_steps]
            length = end - start


            # Ajouter des filtre à intervalles inutiles (genre espace, silence etc.)
            label = self.clean_sampa(label)
            if not self.SAMPA.match(label):
                continue

            yield {
                "label": label,
                "length": length,
                "f0": f0s if f0s != "nan" else None
            }

        shutil.rmtree(self.tts_output_dir)


class Synthetiseur:
    """
    Politique de remplacement des diphones inconnus...
    On a un dictionnaire SAMPA_REPLACEMENTS qui indique
    quel label chercher quand l'un est indiponible
    => la raison et que certains phonèmes sont très proches
       (ex: e et E)

    Si rien n'y fait, qu'aucun diphone ne peut être trouvé,
    on renvoie deux phonèmes qui ne se suivent pas.
    """
    def get_diphone_or_replacement(self, diphones, p1, p2):
        rep1 = SAMPA_REPLACEMENTS.get(p1)
        rep2 = SAMPA_REPLACEMENTS.get(p2)


        if (p1, p2) in diphones:
            return diphones[(p1, p2)]

        if (rep1, p2) in diphones:
            return diphones[(rep1, p2)]

        if (p1, rep2) in diphones:
            return diphones[(p1, rep2)]

        if (rep1, rep2) in diphones:
            return diphones[(rep1, rep2)]

        final_d1 = None
        final_d2 = None
        # Premier tour de boucle pour trouver les
        # bons phonemes
        for ((d1, d2), (dstart, dmiddle1, dmiddle2, dend)) in diphones.items():
            if not final_d1 and p1 == d1:
                final_d1 = (dstart, dmiddle1)
            if not final_d2 and p2 == d2:
                final_d2 = (dmiddle2, dend)

        if not final_d1 or not final_d2:
            raise KeyError((p1, p2))

        (dstart, dmiddle1) = final_d1
        (dmiddle2, dend) = final_d2

        return (dstart, dmiddle1, dmiddle2, dend)

    """
    Nettoie les codes SAMPA fourni par espeak
    """

    def check_diphones(self, phonetic, diphones):
        needed = [(phonetic[i]["label"], phonetic[i+1]["label"]) for i in range(len(phonetic) - 1)]

        missing = [e for e in needed if e not in diphones.keys()]

        if self.use_phonemes:
            if len(missing) > 0:
                print("Les diphones suivants sont manquant, ils seront remplacés par des concaténations de phonèmes")
                for (a, b) in missing:
                    print(f'- {a}{b}')

    def clean_sampa(self, code: str):
        if '-' in code:
            code = code.replace('-', '')
        if code == '2' or code == 'Y':
            code = '@'
        if code == 'A~' or code == 'E~' or code == 'O~':
            code = code.lower()
        return code

    """
    Récupérer son et textgrid
    Construire un dico avec clé phoneme1/phoneme2
    Assigner (start, middle, end)
    Retourner dico
    """
    def voicePhonemes(self, textgrid, textgrid_level=1, textgrid_label="phonemes"):
        # return phonemes
        segms = textgrid[textgrid_label]
        grid_size = len(segms)
        result =  {}
        for i in range(1, grid_size - 1):
            d1 = segms[i]
            d2 = segms[i + 1]

            label_1 = d1.text
            label_2 = d2.text

            start = d1.xmin
            middle = d1.xmax
            end = d2.xmax

            result[(label_1, label_2)] = (start, middle, middle, end)

        return result

    def get_phoneme_from_diphones(self, diphones, label, pos):
        # Pos : true = left / false = right
        for diph, vals in diphones.items():
            (p1, p2) = diph
            (s, m1, m2, e) = vals
            if pos and p1 == label:
                return (s, m1)
            elif not pos and p2 == label:
                return (m2, e)
    """
    Générer la synthèse avec concatenation des diphones
    => Ce faisant, enregistrer le temps de fin + début des phonemes
    Retourner output, phonemes[start, stop]
    """
    def synthesis(self, phonetic_data, voice_sound, diphones):
        # return output, phonemes enrichis par leur temps
        zeroes = call(self.voice_sound, "To PointProcess (zeroes)", 1, "yes", "no")
        blank = voice_sound.extract_part(0, 0.01, WindowShape.RECTANGULAR, 1, False)
        end = voice_sound.extract_part(0, 0.01, WindowShape.RECTANGULAR, 1, False)
        psize = len(phonetic_data)

        output_length = 0.05

        # Boucle à travers les diphones
        for i in range(psize - 1):
            phoneme1_label = phonetic_data[i]["label"]
            phoneme2_label = phonetic_data[i+1]["label"]

            (d_start, d_middle1, d_middle2, d_end) = self.get_diphone_or_replacement(
                diphones,
                phoneme1_label,
                phoneme2_label
            )

            middle1 = (d_start + d_middle1) / 2
            middle2 = (d_middle2 + d_end) / 2


            # On prend comme début de sample
            # Soit le milieu du premier phoneme
            # Soit le début SI c'est le premier diphone
            nearest_idx_1 = call(zeroes, "Get nearest index", d_start if i == 0 else middle1)
            zero_middle_1 = call(zeroes, "Get time from index", nearest_idx_1)

            # On prend comme fin de sample
            # Soit le milieu du second phoneme
            # Soit la fin SI c'est le dernier diphone
            nearest_idx_2 = call(zeroes, "Get nearest index", d_end if i == psize - 2 else middle2)
            zero_middle_2 = call(zeroes, "Get time from index", nearest_idx_2)

            # Si les deux milieux sont identifiques
            # Alors on a affaire à un vrai diphone
            # Sinon, ce sont deux phonemes indépendants
            if d_middle1 == d_middle2:
                sample = voice_sound.extract_part(zero_middle_1, zero_middle_2, WindowShape.RECTANGULAR, 1, False)
            elif self.use_phonemes:
                nearest_idx_center_1 = call(zeroes, "Get nearest index", d_middle1)
                zero_center_1 = call(zeroes, "Get time from index", nearest_idx_center_1)

                nearest_idx_center_2 = call(zeroes, "Get nearest index", d_middle2)
                zero_center_2 = call(zeroes, "Get time from index", nearest_idx_center_2)

                sample1 = voice_sound.extract_part(zero_middle_1, zero_center_1, WindowShape.RECTANGULAR, 1, False)
                sample2 = voice_sound.extract_part(zero_center_2, zero_middle_2, WindowShape.RECTANGULAR, 1, False)

                sample = sample1.concatenate([sample1, sample2])
            else:
                raise Exception(" ".join(["Diphone manquant :", phoneme1_label, phoneme2_label]))

            time_middle_sample = output_length + (d_middle1 - d_start)

            phonetic_data[i]["end"] = time_middle_sample
            phonetic_data[i+1]["start"] = time_middle_sample

            #print("end",phoneme1_label, i, phonetic_data[i]["end"])
            #print("start", phoneme2_label, i+1, phonetic_data[i+1]["start"])

            blank = blank.concatenate([blank, sample])

            output_length += (zero_middle_1 - d_start) + (d_end - zero_middle_2)

        phonetic_data[0]["start"] = 0.05
        phonetic_data[len(phonetic_data) - 1]["end"] = output_length

        blank = blank.concatenate([blank, end])

        return blank, phonetic_data

    """
    (Supprimer marqueurs f0 de l'output)
    Intérer à travers les phonemes
    Appliquer f0 de phoneme[duree, f0]
    Distordre le temps a partir de phoneme[duree, f0]
    Appliquer les changements
    Retourner output
    """
    def postSynthesis(self, pre_output, phonemes):
        # Instance manipulation pre_output (pitch, )
        manipulation = call(pre_output, "To Manipulation", 0.01, 75, 600)

        # Tiers
        pitch_tier = call(manipulation, "Extract pitch tier")
        duration_tier = call(manipulation, "Extract duration tier")

        call(pitch_tier, "Remove points between", 0, pre_output.duration)


        # Pour tout phoneme
        for phoneme in phonemes:

            start = phoneme["start"]
            end = phoneme["end"]

            mid = (start + end) / 2

            length_hypothetic = phoneme["length"]
            length_real = end - start
            length_ratio = length_hypothetic / length_real * 0.50


            # Pitch modifier (4 points de f0 par phonème)
            f0_steps = list(map(lambda x: start + ((end - start) / 5) * x, range(1, 5)))
            for i in range(4):
                f0t = f0_steps[i]
                f0v =  phoneme["f0"][i]
                if not math.isnan(f0v):
                    call(pitch_tier, "Add point", f0t, f0v)

            # Duration modifier
            call(duration_tier, "Add point", start, 1)
            call(duration_tier, "Add point", mid, length_ratio)
            call(duration_tier, "Add point", end, 1)

        call([manipulation, duration_tier], "Replace duration tier")
        call([manipulation, pitch_tier], "Replace pitch tier")

        return call(manipulation, "Get resynthesis (overlap-add)")

    def save(self, sound, filename):
        print(f'Enregistrement de {filename}')
        sound.save(filename, SoundFileFormat.WAV)

    def __init__(
        self,
        sentence,
        voice=("./diphones/logatomes.wav", "./diphones/logatomes.TextGrid"),
        output="output.wav",
        use_phonemes=False,
        phonetizer=PraatPhonetizer()):

        self.use_phonemes = use_phonemes
        (self.voice_sound, self.voice_textGrid) = (Sound(voice[0]), TextGrid(voice[1]))

        # Processing pipeline
        self.diphones = self.voicePhonemes(self.voice_textGrid)
        self.phonetic_data = list(phonetizer.phonetic(sentence))

        # Print la phrase phonetique
        print("".join([a["label"] for a in self.phonetic_data]))

        # Checking diphones availability
        self.check_diphones(self.phonetic_data, self.diphones)

        self.pre_output, self.phonetic_data = self.synthesis(
            self.phonetic_data,
            self.voice_sound,
            self.diphones
        )

        self.output = self.postSynthesis(self.pre_output, self.phonetic_data)

        #self.save(self.pre_output, "pre_" + output)
        self.save(self.output, output)
        #playsound.playsound(self.pre_output)

class SynthetiseurTUI:
    def __init__(self):
        pass

    def run(self):
        pass

"""
synthese = Synthetiseur(
    "Du bristole et de la naphtaline de chez leroy merlin",
    ("./diphones/logatomes.wav", "./diphones/logatomes.TextGrid"),
    output="leroy-merlin.wav",
    use_phonemes=True,
    phonetizer=CoquiTTSPhonetizer()
)
"""

parser = argparse.ArgumentParser(
    prog="./synthese",
    description="Moteur Text-to-Speech à partir de ma voix."
)

parser.add_argument('text', help="Texte à synthétiser")
parser.add_argument(
    '-o', '--output', default="output.wav",
    help="Nom du fichier audio final.")
parser.add_argument(
    '-p', '--never-use-phonemes',
    default=True, action="store_false",
    help="Evite que le programme utilise des phonemes quand des diphones sont indisponibles."
)

args = parser.parse_args()

synthese = Synthetiseur(
    args.text,
    ("./diphones/logatomes.wav", "./diphones/logatomes.TextGrid"),
    output=args.output,
    use_phonemes=args.never_use_phonemes,
    phonetizer=CoquiTTSPhonetizer()
)
