import fitz  # PyMuPDF
import re
import os
from bs4 import BeautifulSoup
from docx import Document
from docx.opc.exceptions import PackageNotFoundError


def extract_pdf(filepath):
    doc = fitz.open(filepath)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text

def extract_docx(filepath):
    try:
        doc = Document(filepath)
        return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    except PackageNotFoundError as exc:
        print(f"[EXTRACT_DOCX] Invalid DOCX package: {filepath} ({exc})")
        return ""
    except Exception as exc:
        print(f"[EXTRACT_DOCX] Failed to read DOCX {filepath}: {exc}")
        return ""


def extract_html(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        html = f.read()
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(["nav", "footer", "script", "style", "header", "noscript"]):
        tag.decompose()
    return soup.get_text(separator="\n")


def extract_txt(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def extract_text(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.pdf':
        return extract_pdf(filepath)
    elif ext == '.docx':
        return extract_docx(filepath)
    elif ext in {'.html', '.htm'}:
        return extract_html(filepath)
    elif ext == '.txt':
        return extract_txt(filepath)
    return ""

def clean_text(text):
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n ', '\n', text)
    return text.strip()

def chunk_text(text, chunk_size=600, overlap=100):
    """Split text into overlapping word chunks."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = ' '.join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
        i += chunk_size - overlap
    return chunks

def ingest_folder(folder_path, subject, module=None, source_type="local"):
    """Ingest all documents from a folder and return chunks with metadata."""
    all_chunks = []
    
    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            if filename.startswith('.'):
                continue
            filepath = os.path.join(root, filename)
            
            safe_filename = filename.encode('cp1252', errors='replace').decode('cp1252')
            print(f"  Processing: {safe_filename}")
            
            try:
                raw_text = extract_text(filepath)
            except Exception as exc:
                print(f"[INGEST_FOLDER] Failed to extract text from {filepath}: {exc}")
                continue
            if not raw_text or len(raw_text) < 100:
                continue
            
            clean = clean_text(raw_text)
            chunks = chunk_text(clean)
            
            # Infer module from subfolder name if not provided
            subfolder = os.path.basename(root)
            inferred_module = module or (subfolder if subfolder != os.path.basename(folder_path) else "General")
            
            for i, chunk in enumerate(chunks):
                all_chunks.append({
                    "content": chunk,
                    "subject": subject,
                    "module": inferred_module,
                    "source": filename,
                    "filepath": filepath,
                    "source_type": source_type,
                    "url_or_path": filepath,
                })
    
    return all_chunks
