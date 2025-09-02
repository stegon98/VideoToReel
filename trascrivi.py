import os
import subprocess
from pyannote.audio import Pipeline
from faster_whisper import WhisperModel
import json
from datetime import timedelta
import re
import torch

# --- CONFIGURAZIONE ---
# Specifica la lingua per la trascrizione
# Usa "en" per l'inglese, "it" per l'italiano o "" per il rilevamento automatico.
LANGUAGE = "en"
# --- FINE CONFIGURAZIONE ---

# NUOVA FUNZIONE: per formattare i secondi in un formato timestamp leggibile
def format_timestamp(seconds):
    """Converte i secondi (float) in una stringa di timestamp HH:MM:SS,mmm."""
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = td.microseconds // 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

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
    """Identifica i segmenti di parlato per ogni altoparlante, usando la GPU se disponibile."""
    print("Avvio diarizzazione degli altoparlanti...")

    # 2. SELEZIONA IL DISPOSITIVO (GPU o CPU)
    # Controlla se il backend MPS (per GPU Apple Silicon) è disponibile
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Utilizzo del dispositivo per la diarizzazione: {device.upper()}")

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=True # Sostituisci con il tuo token se hai problemi
    )

    # 3. SPOSTA LA PIPELINE SUL DISPOSITIVO SELEZIONATO
    pipeline.to(torch.device(device))
    diarization = pipeline(audio_path)
    segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append({'start': turn.start, 'end': turn.end, 'speaker': speaker})
    print("Diarizzazione completata.")
    return segments

def trascrivi_audio(audio_path, language):
    """Trascrive l'audio usando faster-whisper e ottiene i timestamp per ogni parola."""
    print("Avvio trascrizione audio con faster-whisper...")
    # 'medium' è un buon compromesso, 'large-v2' è più accurato
    model = WhisperModel("medium", device="auto", compute_type="int8")

    segments, _ = model.transcribe(audio_path, language=language, word_timestamps=True)

    result = []
    for segment in segments:
        words = []
        if segment.words:
            for word in segment.words:
                words.append({'start': word.start, 'end': word.end, 'word': word.word.strip()})
        result.append({'start': segment.start, 'end': segment.end, 'text': segment.text.strip(), 'words': words})

    print("Trascrizione completata.")
    return result

# MODIFICATA: la funzione ora salva sia il JSON che il TXT
def unisci_e_salva_risultati(diarizzazione, trascrizione, output_json_file, output_txt_file):
    """Combina i risultati e li salva in un file JSON e in un file TXT."""
    print("Combinazione dei risultati...")

    # Assegna gli altoparlanti ai segmenti di trascrizione
    for seg_transc in trascrizione:
        seg_start_ms = seg_transc['start']
        seg_end_ms = seg_transc['end']

        # Trova l'altoparlante il cui segmento di diarizzazione ha la maggiore sovrapposizione
        best_speaker = "Unknown"
        max_overlap = 0

        for seg_diar in diarizzazione:
            overlap_start = max(seg_start_ms, seg_diar['start'])
            overlap_end = min(seg_end_ms, seg_diar['end'])
            overlap = overlap_end - overlap_start

            if overlap > max_overlap:
                max_overlap = overlap
                best_speaker = seg_diar['speaker']

        seg_transc['speaker'] = best_speaker

    # 1. Salva il file JSON
    with open(output_json_file, 'w', encoding='utf-8') as f:
        json.dump(trascrizione, f, ensure_ascii=False, indent=2)
    print(f"File JSON finale salvato in '{output_json_file}'.")

    # 2. Salva il file TXT
    with open(output_txt_file, 'w', encoding='utf-8') as f:
        for segment in trascrizione:
            start_time = format_timestamp(segment['start'])
            end_time = format_timestamp(segment['end'])
            speaker = segment['speaker']
            text = segment['text']

            # Scrive la riga formattata nel file
            f.write(f"[{start_time} --> {end_time}] {speaker}: {text}\n")

    print(f"Trascrizione testuale salvata in '{output_txt_file}'.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Trascrive e diarizza un video MP4/WEBM.")
    parser.add_argument("input_file", type=str, help="Percorso del file video di input (es. video.mp4).")
    args = parser.parse_args()

    file_video_input = args.input_file
    base_name = os.path.splitext(file_video_input)[0]

    # MODIFICATO: Definiamo i percorsi di output per entrambi i file
    output_json = base_name + ".json"
    output_txt = base_name + ".txt"
    percorso_audio = "temp_audio.wav"

    try:
        audio_estratto = estrai_audio(file_video_input, percorso_audio)
        if audio_estratto:
            diarizzazione_result = diarizza_audio(audio_estratto)
            trascrizione_result = trascrivi_audio(audio_estratto, LANGUAGE)

            # MODIFICATO: Passiamo entrambi i nomi dei file di output alla funzione
            unisci_e_salva_risultati(diarizzazione_result, trascrizione_result, output_json, output_txt)

            os.remove(audio_estratto)
            print("Processo completato.")
    except Exception as e:
        print(f"\n❌ Errore: {e}")