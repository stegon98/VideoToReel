import os
import subprocess
import json
import pysubs2
from datetime import timedelta
import re
import argparse

# --- FUNZIONI DI SUPPORTO ---
def parse_time(time_str):
    """Converte una stringa di tempo [H:MM:SS] in un oggetto timedelta."""
    parts = list(map(int, time_str.strip('[]').split(':')))
    if len(parts) == 2:
        return timedelta(minutes=parts[0], seconds=parts[1])
    elif len(parts) == 3:
        return timedelta(hours=parts[0], minutes=parts[1], seconds=parts[2])
    return None

def find_clip_boundaries(segments, question, answer):
    """Trova i tempi di inizio e fine per il reel basandosi sulla domanda e risposta."""
    print("Ricerca dei tempi per la domanda e la risposta...")
    start_reel = None
    end_reel = None

    for segment in segments:
        if question.strip() in segment['text']:
            start_reel = segment['start']
            print(f"✅ Trovato inizio reel (domanda) a: {start_reel}")
            break

    for segment in segments:
        if answer.strip() in segment['text']:
            end_reel = segment['end']
            print(f"✅ Trovato fine reel (risposta) a: {end_reel}")
            break

    if start_reel is None or end_reel is None:
        raise ValueError("Impossibile trovare la domanda o la risposta nel file di testo.")

    return start_reel, end_reel

def create_ass_file(segments, ass_path="temp_subtitles.ass"):
    """
    Crea un file di sottotitoli in formato .ass con l'effetto karaoke e formattazione a 2 righe.
    """
    print(f"Creazione del file di sottotitoli temporaneo con effetto karaoke: {ass_path}")

    subs = pysubs2.SSAFile()

    # Definisci uno stile per i sottotitoli evidenziati (Ciano)
    # Non è necessario lo stile BaseText se non lo useremo
    subs.styles["Default"] = pysubs2.SSAStyle(
        fontname="Arial",
        fontsize=28,
        primarycolor=pysubs2.Color(0, 255, 255), # Ciano/Aqua (colore principale)
        outlinecolor=pysubs2.Color(0, 0, 0),    # Nero (bordo)
        outline=2,
        shadow=1,
        marginv=70,
        alignment=2 # In basso al centro
    )

    # Raccogli tutte le parole con i loro timestamp da tutti i segmenti
    all_words_with_timestamps = []
    for segment in segments:
        for word_info in segment['words']:
            all_words_with_timestamps.append({
                'start': word_info['start'],
                'end': word_info['end'],
                'text': word_info['word']
            })

    # Crea un evento di sottotitolo per ogni parola
    # Questa è la logica che ti darà l'effetto "parola per parola"
    for word_data in all_words_with_timestamps:
        event = pysubs2.SSAEvent(
            start=int(word_data['start'] * 1000),
            end=int(word_data['end'] * 1000),
            text=word_data['text'],
            style="Default" # Usa lo stile ciano per ogni parola
        )
        subs.append(event)

    # Ordina gli eventi per tempo di inizio per assicurare il rendering corretto
    subs.sort()

    subs.save(ass_path, format='ass')
    return ass_path

def generate_reel(video_path, ass_path, start_time, end_time, output_path):
    """Usa FFmpeg per tagliare il video, ritagliarlo in formato reel e imprimere i sottotitoli."""
    print(f"Avvio di FFmpeg per generare il reel: {output_path}")

    start_str = str(timedelta(seconds=start_time))
    end_str = str(timedelta(seconds=end_time))

    # Comando FFmpeg per il formato Reel
    # Aggiunti i filtri -vf per il ridimensionamento e il ritaglio in formato 9:16
    command = [
        "ffmpeg",
        "-i", video_path,
        "-ss", start_str,
        "-to", end_str,
        "-vf", f"crop=ih*(9/16):ih,ass={ass_path}",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "192k",
        "-y",
        output_path  # Deve essere qualcosa tipo 'video_output.mp4'
    ]




    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        print(f"\n🎉 Reel generato con successo: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Errore durante l'esecuzione di FFmpeg: {e.stderr}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crea un reel video da una porzione di testo.")
    parser.add_argument("video_file", type=str, help="Percorso del file video originale (es. video.mp4).")
    parser.add_argument("text_file", type=str, help="Percorso del file JSON generato (es. video.json).")
    parser.add_argument("question", type=str, help="La porzione di testo della domanda.")
    parser.add_argument("answer", type=str, help="La porzione di testo della risposta.")
    args = parser.parse_args()

    percorso_ass = "temp_subtitles.ass"

    try:
        with open(args.text_file, 'r', encoding='utf-8') as f:
            segments = json.load(f)

        start_reel, end_reel = find_clip_boundaries(segments, args.question, args.answer)
        percorso_ass_file = create_ass_file(segments, percorso_ass)

        output_name = f"{os.path.splitext(os.path.basename(args.video_file))[0]}_reel.mp4"
        generate_reel(args.video_file, percorso_ass_file, start_reel, end_reel, output_name)

        os.remove(percorso_ass_file)
        print("File temporanei rimossi.")

    except (ValueError, FileNotFoundError) as e:
        print(f"\n❌ Errore: {e}")