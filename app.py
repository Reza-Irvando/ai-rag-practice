import os
import chromadb
import requests
from dotenv import load_dotenv

# ==========================================================
# PENGATURAN MODE EKSEKUSI
# Set True untuk Ollama (Lokal/Gratis)
# Set False untuk Google Gemini API
# ==========================================================
USE_OLLAMA = True

OLLAMA_MODEL = "llama3.2"
GEMINI_MODEL = "gemini-3.8-flash"

load_dotenv()

# Inisialisasi client Gemini jika mode Gemini aktif
gemini_client = None
if not USE_OLLAMA:
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY tidak ditemukan di file .env!")
    gemini_client = genai.Client(api_key=api_key)

# 1. Inisialisasi Vector Database (ChromaDB lokal in-memory)
chroma_client = chromadb.Client()

# Reset atau buat koleksi baru
collection = chroma_client.get_or_create_collection(name="pengetahuan_kantor")

# 2. Dokumen Pengetahuan Perusahaan
dokumen = [
    "Aturan Cuti: Karyawan berhak atas 12 hari cuti tahunan setelah masa kerja 1 tahun.",
    "Reimbursement Medis: Batas klaim rawat jalan maksimal Rp5.000.000 per tahun per karyawan.",
    "Prosedur Perjalanan Dinas: Tiket pesawat kelas ekonomi harus dipesan minimal 7 hari sebelum keberangkatan.",
    "Jam Kerja: Jam operasional kantor adalah Senin sampai Jumat, pukul 09.00 hingga 18.00 WIB.",
]

# Masukkan dokumen ke ChromaDB jika koleksi masih kosong
if collection.count() == 0:
    collection.add(
        documents=dokumen,
        ids=[f"doc_{i}" for i in range(len(dokumen))],
    )

print(
    f"[INFO] Vector DB Siap ({collection.count()} dokumen terindeks). Engine aktif: {'Ollama (' + OLLAMA_MODEL + ')' if USE_OLLAMA else 'Gemini API'}\n"
)


def panggil_ollama(system_prompt: str, user_prompt: str) -> str:
    """Memanggil API lokal Ollama via HTTP request."""
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }
    try:
        res = requests.post(url, json=payload, timeout=60)
        res.raise_for_status()
        return res.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return "[ERROR] Tidak dapat terhubung ke Ollama. Pastikan aplikasi Ollama aktif di latar belakang!"
    except Exception as e:
        return f"[ERROR] Gagal memanggil Ollama: {str(e)}"


def panggil_gemini(system_prompt: str, user_prompt: str) -> str:
    """Memanggil Google Gemini API."""
    try:
        from google.genai import types

        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.1,
            ),
        )
        return response.text
    except Exception as e:
        return f"[ERROR] Gagal memanggil Gemini: {str(e)}"


def rag_chat(pertanyaan_user: str) -> str:
    # 3. Retrieval: Ambil 3 dokumen terdekat agar peluang kecocokan konteks tinggi
    results = collection.query(query_texts=[pertanyaan_user], n_results=3)
    dokumen_ditemukan = results["documents"][0]

    # DEBUG: Menampilkan apa yang sebenarnya ditemukan oleh Vector DB
    print("\n--- [DEBUG: Dokumen yang Ditarik Vector DB] ---")
    for idx, d in enumerate(dokumen_ditemukan, 1):
        print(f"[{idx}] {d}")
    print("----------------------------------------------\n")

    konteks_terkait = "\n".join(dokumen_ditemukan)

    # 4. Prompt yang lebih fleksibel terhadap sinonim & padanan kata
    system_instruction = (
        "Kamu adalah asisten HRD internal. Jawab pertanyaan pengguna berdasarkan "
        "potongan konteks dokumen yang diberikan. Pahami sinonim umum dalam bahasa Indonesia "
        "(misalnya 'mengajukan tiket' setara maknanya dengan 'memesan tiket'). "
        "Jawab dengan langsung, jelas, dan akurat. "
        "Jika informasinya sama sekali tidak berkaitan atau tidak ada di konteks, "
        "baru katakan: 'Informasi tidak ditemukan di dokumen panduan.'"
    )

    user_prompt = f"""Konteks Dokumen:
{konteks_terkait}

Pertanyaan Karyawan: {pertanyaan_user}"""

    # 5. Routing pemanggilan model
    if USE_OLLAMA:
        return panggil_ollama(system_instruction, user_prompt)
    else:
        return panggil_gemini(system_instruction, user_prompt)


# 6. Loop Percakapan di Terminal
if __name__ == "__main__":
    while True:
        tanya = input("\nTanya ke Dokumen (atau ketik 'exit' untuk keluar): ")
        if tanya.strip().lower() == "exit":
            print("Selesai.")
            break
        if not tanya.strip():
            continue

        jawaban = rag_chat(tanya)
        print(f"Jawaban ({'Ollama' if USE_OLLAMA else 'Gemini'}):\n{jawaban}\n")