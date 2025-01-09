import random
import random
import os
import torch
import requests
import shutil
import re
import xml.etree.ElementTree as ET

from textgrids import TextGrid
from TTS.api import TTS
from parselmouth import Sound
from parselmouth.praat import call

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
