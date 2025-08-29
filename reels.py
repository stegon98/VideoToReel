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

    # Definisci lo stile dei sottotitoli
    subs.styles["Default"].fontname = "Arial"
    subs.styles["Default"].fontsize = 28
    subs.styles["Default"].primarycolor = pysubs2.Color(255, 255, 255) # Testo non evidenziato (Bianco)
    subs.styles["Default"].secondarycolor = pysubs2.Color(0, 255, 255) # Testo evidenziato (Ciano)
    subs.styles["Default"].outlinecolor = pysubs2.Color(0, 0, 0) # Bordo (Nero)
    subs.styles["Default"].backcolor = pysubs2.Color(0, 0, 0, 0) # Sfondo del testo
    subs.styles["Default"].outline = 2
    subs.styles["Default"].shadow = 1
    subs.styles["Default"].alignment = 2 # In basso al centro

    # Combina le parole in linee di massimo 6 parole
    all_words = []
    for segment in segments:
        for word_info in segment['words']:
            all_words.append({'start': word_info['start'], 'end': word_info['end'], 'text': word_info['word']})

    current_line = []
    current_line_count = 0
    current_line_start = None

    for i, word in enumerate(all_words):
        current_line.append(word)

        if len(current_line) == 6 or i == len(all_words) - 1:
            line_text = ""
            for w in current_line:
                # La durata del karaoke è la durata della parola
                duration_ms = int((w['end'] - w['start']) * 1000)
                line_text += f"{{\\k{duration_ms}}}{w['text']} "

            line_start_ms = int(current_line[0]['start'] * 1000)
            line_end_ms = int(current_line[-1]['end'] * 1000)

            event = pysubs2.SSAEvent(
                start=line_start_ms,
                end=line_end_ms,
                text=line_text.strip()
            )
            subs.append(event)

            current_line = []

    subs.save(ass_path, format='ass')
    return ass_path

def generate_reel(video_path, ass_path, start_time, end_time, output_path):
    """Usa FFmpeg per tagliare il video e imprimere i sottotitoli."""
    print(f"Avvio di FFmpeg per generare il reel: {output_path}")

    start_str = str(timedelta(seconds=start_time))
    end_str = str(timedelta(seconds=end_time))

    command = [
        "ffmpeg",
        "-i", video_path,
        "-ss", start_str,
        "-to", end_str,
        "-vf", f"ass={ass_path}",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "192k",
        "-y",
        output_path
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