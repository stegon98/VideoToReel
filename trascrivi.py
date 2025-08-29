import os
import subprocess
from pyannote.audio import Pipeline
from faster_whisper import WhisperModel
import json
from datetime import timedelta
import re

# --- CONFIGURAZIONE ---
# Specifica la lingua per la trascrizione
# Usa "en" per l'inglese, "it" per l'italiano o "" per il rilevamento automatico.
LANGUAGE = "it"
# --- FINE CONFIGURAZIONE ---

def estrai_audio(video_path, audio_path="temp_audio.wav"):
    """Estrae l'audio da un file video (MP4/WEBM) in formato WAV."""
    print(f"Estrazione dell'audio da '{video_path}'...")
    command = ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", "-y", audio_path]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        print(f"Audio estratto e salvato in '{audio_path}'.")
        return audio_path
    except subprocess.CalledProcessError as e:
        print("❌ Errore durante l'estrazione dell'audio con FFmpeg.")
        print(f"Errore: {e.stderr}")
        return None

def diarizza_audio(audio_path):
    """Identifica i segmenti di parlato per ogni altoparlante."""
    print("Avvio diarizzazione degli altoparlanti...")
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=True # Sostituisci con il tuo token se hai problemi
    )
    diarization = pipeline(audio_path)
    segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append({'start': turn.start, 'end': turn.end, 'speaker': speaker})
    print("Diarizzazione completata.")
    return segments

def trascrivi_audio(audio_path, language):
    """Trascrive l'audio usando faster-whisper e ottiene i timestamp per ogni parola."""
    print("Avvio trascrizione audio con fa  ster-whisper...")
    # 'medium' è un buon compromesso, 'large-v2' è più accurato
    # Usiamo 'cpu' per evitare l'errore di compatibilità con MPS, ma sfrutta comunque la CPU M4
    model = WhisperModel("medium", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_path, language=language, word_timestamps=True)

    result = []
    for segment in segments:
        words = []
        if segment.words:
            for word in segment.words:
                print(f"parola->{word}")
                words.append({'start': word.start, 'end': word.end, 'word': word.word.strip()})
        result.append({'start': segment.start, 'end': segment.end, 'text': segment.text.strip(), 'words': words})

    print("Trascrizione completata.")
    return result

def unisci_e_salva_json(diarizzazione, trascrizione, output_file):
    """Combina i risultati e li salva in un unico file JSON."""
    print("Combinazione dei risultati e salvataggio in JSON...")

    # Crea una mappa per una ricerca più veloce
    diar_map = {}
    for seg in diarizzazione:
        start_ms = int(seg['start'] * 1000)
        end_ms = int(seg['end'] * 1000)
        diar_map[start_ms] = {'speaker': seg['speaker'], 'end_ms': end_ms}

    # Assegna gli altoparlanti ai segmenti di trascrizione
    for seg_transc in trascrizione:
        seg_start_ms = int(seg_transc['start'] * 1000)
        seg_end_ms = int(seg_transc['end'] * 1000)

        # Trova l'altoparlante
        speaker = "Unknown"
        min_diff = float('inf')
        for start_diar, diar_info in diar_map.items():
            diff = abs(start_diar - seg_start_ms)
            if diff < min_diff:
                min_diff = diff
                speaker = diar_info['speaker']

        seg_transc['speaker'] = speaker

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(trascrizione, f, ensure_ascii=False, indent=2)

    print(f"File JSON finale salvato in '{output_file}'.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Trascrive e diarizza un video MP4/WEBM.")
    parser.add_argument("input_file", type=str, help="Percorso del file video di input (es. video.mp4).")
    args = parser.parse_args()

    file_video_input = args.input_file
    output_json = os.path.splitext(file_video_input)[0] + ".json"
    percorso_audio = "temp_audio.wav"

    try:
        audio_estratto = estrai_audio(file_video_input, percorso_audio)
        if audio_estratto:
            diarizzazione_result = diarizza_audio(audio_estratto)
            trascrizione_result = trascrivi_audio(audio_estratto, LANGUAGE)
            unisci_e_salva_json(diarizzazione_result, trascrizione_result, output_json)
            os.remove(audio_estratto)
            print("Processo completato.")
    except Exception as e:
        print(f"\n❌ Errore: {e}")