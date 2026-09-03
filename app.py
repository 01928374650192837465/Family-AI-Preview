"""
Family AI Server - single-file Streamlit application.

Local stack:
  - Ollama (http://localhost:11434) running the multimodal model `qwen2.5-vl`
  - ChromaDB persistent vector memory under C:\\FamilyAI_Data
  - Pillow for image handling
  - CPU-side deterministic math interceptor

Run:
    streamlit run app.py --server.address 0.0.0.0 --server.port 8501
"""

from __future__ import annotations

import ast
import io
import json
import operator
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import chromadb
import ollama
import streamlit as st
from chromadb.config import Settings
from PIL import Image

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - fallback for older installs
    from PyPDF2 import PdfReader  # type: ignore


# --------------------------------------------------------------------------- #
# Constants & storage layout
# --------------------------------------------------------------------------- #

MODEL_NAME = "qwen2.5-vl"
OLLAMA_HOST = "http://localhost:11434"

BASE_DIR = Path(r"C:\FamilyAI_Data")
CHROMA_DIR = BASE_DIR / "vector_store"
ROOMS_DIR = BASE_DIR / "rooms"
UPLOADS_DIR = BASE_DIR / "uploads"
INDEX_FILE = BASE_DIR / "rooms_index.json"

for _directory in (BASE_DIR, CHROMA_DIR, ROOMS_DIR, UPLOADS_DIR):
    _directory.mkdir(parents=True, exist_ok=True)

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
TOP_K = 4

CPU_POOL = ThreadPoolExecutor(max_workers=max(4, (os.cpu_count() or 8)))


# --------------------------------------------------------------------------- #
# Page configuration
# --------------------------------------------------------------------------- #

st.set_page_config(
    page_title="Family AI Server",
    page_icon="ð ",
    layout="wide",
    initial_sidebar_state="expanded",
)


# --------------------------------------------------------------------------- #
# Persistence helpers (rooms index + per-room transcripts)
# --------------------------------------------------------------------------- #


def load_rooms_index() -> Dict[str, Dict[str, Any]]:
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_rooms_index(index: Dict[str, Dict[str, Any]]) -> None:
    INDEX_FILE.write_text(json.dumps(index, indent=2), encoding="utf-8")


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return slug or "room"


def room_collection_name(room_id: str) -> str:
    # Chroma collection names: 3-63 chars, alphanumeric plus _ and -.
    return f"room_{room_id}"[:63]


def room_history_path(room_id: str) -> Path:
    return ROOMS_DIR / f"{room_id}.json"


def load_history(room_id: str) -> List[Dict[str, Any]]:
    path = room_history_path(room_id)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_history(room_id: str, history: List[Dict[str, Any]]) -> None:
    room_history_path(room_id).write_text(
        json.dumps(history, indent=2), encoding="utf-8"
    )


def create_room(name: str) -> str:
    index = load_rooms_index()
    room_id = f"{slugify(name)}_{uuid.uuid4().hex[:8]}"
    index[room_id] = {
        "name": name.strip(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "collection": room_collection_name(room_id),
        "files": [],
    }
    save_rooms_index(index)
    save_history(room_id, [])
    (UPLOADS_DIR / room_id).mkdir(parents=True, exist_ok=True)
    return room_id


def delete_room(room_id: str) -> None:
    index = load_rooms_index()
    meta = index.pop(room_id, None)
    save_rooms_index(index)

    path = room_history_path(room_id)
    if path.exists():
        path.unlink()

    if meta:
        try:
            get_chroma_client().delete_collection(meta["collection"])
        except Exception:
            pass

    room_uploads = UPLOADS_DIR / room_id
    if room_uploads.exists():
        for file_path in room_uploads.iterdir():
            try:
                file_path.unlink()
            except OSError:
                pass
        try:
            room_uploads.rmdir()
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# ChromaDB (persistent local vector memory)
# --------------------------------------------------------------------------- #


@st.cache_resource(show_spinner=False)
def get_chroma_client() -> chromadb.ClientAPI:
    return chromadb.PersistentClient(
        path=str(CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False, allow_reset=False),
    )


def get_collection(room_id: str):
    """Return the vector collection scoped strictly to one chat room."""
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=room_collection_name(room_id),
        metadata={"hnsw:space": "cosine", "room_id": room_id},
    )


# --------------------------------------------------------------------------- #
# Document ingestion: extraction, chunking, vectorization
# --------------------------------------------------------------------------- #


def extract_text_from_pdf(raw: bytes) -> str:
    reader = PdfReader(io.BytesIO(raw))
    pages: List[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return "\n\n".join(pages)


def extract_text_from_txt(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    clean = re.sub(r"[ \t]+", " ", text)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    if not clean:
        return []

    chunks: List[str] = []
    start = 0
    length = len(clean)
    while start < length:
        end = min(start + size, length)
        if end < length:
            window = clean.rfind(" ", start + int(size * 0.6), end)
            if window != -1:
                end = window
        piece = clean[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return chunks


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed via the local Ollama engine; falls back to Chroma's default if absent."""
    client = get_ollama_client()
    vectors: List[List[float]] = []
    for text in texts:
        response = client.embeddings(model=MODEL_NAME, prompt=text)
        vectors.append(list(response["embedding"]))
    return vectors


def ingest_document(room_id: str, filename: str, raw: bytes) -> Tuple[int, str]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        text = extract_text_from_pdf(raw)
    elif suffix == ".txt":
        text = extract_text_from_txt(raw)
    else:
        return 0, f"Unsupported document type: {suffix}"

    chunks = chunk_text(text)
    if not chunks:
        return 0, f"No readable text found in {filename}."

    collection = get_collection(room_id)
    doc_id = uuid.uuid4().hex[:10]
    ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "room_id": room_id,
            "source": filename,
            "chunk": i,
            "ingested_at": datetime.now().isoformat(timespec="seconds"),
        }
        for i in range(len(chunks))
    ]

    try:
        embeddings = embed_texts(chunks)
        collection.add(
            ids=ids, documents=chunks, metadatas=metadatas, embeddings=embeddings
        )
    except Exception:
        # Ollama embedding endpoint unavailable for this model -> use Chroma default.
        collection.add(ids=ids, documents=chunks, metadatas=metadatas)

    # Persist a copy of the raw file inside the room's private folder.
    room_uploads = UPLOADS_DIR / room_id
    room_uploads.mkdir(parents=True, exist_ok=True)
    (room_uploads / filename).write_bytes(raw)

    index = load_rooms_index()
    if room_id in index:
        files = index[room_id].setdefault("files", [])
        if filename not in files:
            files.append(filename)
        save_rooms_index(index)

    return len(chunks), f"Indexed {len(chunks)} chunks from {filename}."


def retrieve_context(room_id: str, query: str, top_k: int = TOP_K) -> List[Dict[str, Any]]:
    collection = get_collection(room_id)
    try:
        if collection.count() == 0:
            return []
    except Exception:
        return []

    try:
        try:
            query_embedding = embed_texts([query])[0]
            result = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, max(collection.count(), 1)),
            )
        except Exception:
            result = collection.query(
                query_texts=[query], n_results=min(top_k, max(collection.count(), 1))
            )
    except Exception:
        return []

    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[None] * len(documents)])[0]

    hits: List[Dict[str, Any]] = []
    for doc, meta, dist in zip(documents, metadatas, distances):
        hits.append({"text": doc, "meta": meta or {}, "distance": dist})
    return hits


def build_reference_block(hits: Iterable[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for i, hit in enumerate(hits, start=1):
        source = hit["meta"].get("source", "memory")
        lines.append(f"[{i}] (source: {source})\n{hit['text']}")
    if not lines:
        return ""
    return (
        "REFERENCE BLOCK - retrieved from this chat room's private local memory. "
        "Use it when relevant and cite the source file name.\n\n"
        + "\n\n".join(lines)
    )


# --------------------------------------------------------------------------- #
# Autonomous CPU math interceptor
# --------------------------------------------------------------------------- #

MATH_PATTERN = re.compile(
    r"(?<![\w.])"                     # not glued to a word
    r"(\d+(?:\.\d+)?(?:\s*[\+\-\*/%^]\s*|\s*\*\*\s*)"  # first operand + operator
    r"(?:\(?\s*\d+(?:\.\d+)?\s*\)?\s*(?:[\+\-\*/%^]|\*\*)?\s*)+)"
)

SAFE_BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
SAFE_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

MAX_POW_EXPONENT = 512


def _safe_eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("Only numeric literals are allowed.")
        return node.value
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in SAFE_BINARY_OPS:
            raise ValueError("Unsupported operator.")
        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)
        if op_type is ast.Pow and abs(right) > MAX_POW_EXPONENT:
            raise ValueError("Exponent too large for the safe sandbox.")
        return SAFE_BINARY_OPS[op_type](left, right)
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in SAFE_UNARY_OPS:
            raise ValueError("Unsupported unary operator.")
        return SAFE_UNARY_OPS[op_type](_safe_eval_node(node.operand))
    raise ValueError("Expression contains a disallowed construct.")


def safe_calculate(expression: str) -> float:
    """Evaluate an arithmetic-only expression inside a hardened AST sandbox."""
    normalized = expression.replace("^", "**").replace("x", "*").strip()
    normalized = re.sub(r"[^0-9\.\+\-\*/%\(\) ]", "", normalized)
    if len(normalized) > 200:
        raise ValueError("Expression too long.")
    tree = ast.parse(normalized, mode="eval")
    return _safe_eval_node(tree)


def format_number(value: float) -> str:
    if isinstance(value, float) and value.is_integer():
        return f"{int(value):,}"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:,.10g}"


def extract_math_expressions(text: str) -> List[str]:
    found: List[str] = []
    for match in MATH_PATTERN.finditer(text):
        candidate = match.group(1).strip().rstrip("+-*/%^ ")
        if not re.search(r"[\+\-\*/%^]", candidate):
            continue
        if candidate not in found:
            found.append(candidate)
    return found[:5]


def run_math_interceptor(text: str) -> List[Tuple[str, str]]:
    """Compute detected expressions on local CPU threads. Returns (expr, result)."""
    expressions = extract_math_expressions(text)
    if not expressions:
        return []

    futures = {expr: CPU_POOL.submit(safe_calculate, expr) for expr in expressions}
    results: List[Tuple[str, str]] = []
    for expr, future in futures.items():
        try:
            results.append((expr, format_number(future.result(timeout=5))))
        except Exception:
            continue
    return results


# --------------------------------------------------------------------------- #
# Ollama backend
# --------------------------------------------------------------------------- #


@st.cache_resource(show_spinner=False)
def get_ollama_client() -> ollama.Client:
    return ollama.Client(host=OLLAMA_HOST)


def check_backend() -> Tuple[bool, str]:
    try:
        listing = get_ollama_client().list()
        models = [m.get("model", m.get("name", "")) for m in listing.get("models", [])]
        installed = any(str(m).startswith(MODEL_NAME) for m in models)
        if installed:
            return True, f"Ollama online Â· {MODEL_NAME} ready"
        return False, f"Ollama online, but `{MODEL_NAME}` is not pulled. Run: ollama pull {MODEL_NAME}"
    except Exception as exc:
        return False, f"Ollama unreachable at {OLLAMA_HOST} ({exc})"


SYSTEM_PROMPT = (
    "You are the household's private AI assistant, running entirely on a local "
    "Windows 11 server with an NVIDIA RTX 5070 Ti. You answer clearly and "
    "concisely for family members of all ages. When a REFERENCE BLOCK is "
    "supplied, ground your answer in it and name the source file. When a "
    "VERIFIED CALCULATION block is supplied, treat those numbers as absolute "
    "truth and never recompute or contradict them. Never invent facts."
)


def build_messages(
    history: List[Dict[str, Any]],
    user_text: str,
    reference_block: str,
    math_block: str,
    image_bytes: Optional[List[bytes]],
    max_turns: int = 12,
) -> List[Dict[str, Any]]:
    messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    for entry in history[-max_turns:]:
        messages.append({"role": entry["role"], "content": entry["content"]})

    prompt_parts: List[str] = []
    if reference_block:
        prompt_parts.append(reference_block)
    if math_block:
        prompt_parts.append(math_block)
    prompt_parts.append(f"USER QUESTION:\n{user_text}")

    user_message: Dict[str, Any] = {"role": "user", "content": "\n\n".join(prompt_parts)}
    if image_bytes:
        user_message["images"] = image_bytes
    messages.append(user_message)
    return messages


def stream_ollama(messages: List[Dict[str, Any]]):
    client = get_ollama_client()
    stream = client.chat(
        model=MODEL_NAME,
        messages=messages,
        stream=True,
        options={"temperature": 0.4, "num_ctx": 8192},
    )
    for chunk in stream:
        piece = chunk.get("message", {}).get("content", "")
        if piece:
            yield piece


# --------------------------------------------------------------------------- #
# Session state (per browser session -> no cross-contamination)
# --------------------------------------------------------------------------- #


def init_session_state() -> None:
    if "session_id" not in st.session_state:
        st.session_state.session_id = uuid.uuid4().hex

    if "rooms" not in st.session_state:
        st.session_state.rooms = load_rooms_index()

    if not st.session_state.rooms:
        default_id = create_room("General Family Chat")
        st.session_state.rooms = load_rooms_index()
        st.session_state.active_room = default_id

    if "active_room" not in st.session_state or st.session_state.active_room not in st.session_state.rooms:
        st.session_state.active_room = next(iter(st.session_state.rooms))

    if "histories" not in st.session_state:
        st.session_state.histories = {}

    room_id = st.session_state.active_room
    if room_id not in st.session_state.histories:
        st.session_state.histories[room_id] = load_history(room_id)

    if "ingested" not in st.session_state:
        st.session_state.ingested = {}
    st.session_state.ingested.setdefault(room_id, set())


init_session_state()


# --------------------------------------------------------------------------- #
# Sidebar: workspace manager
# --------------------------------------------------------------------------- #

with st.sidebar:
    st.title("ð  Family AI Server")

    online, status_message = check_backend()
    (st.success if online else st.error)(status_message)

    st.divider()
    st.subheader("Chat Rooms")

    rooms = st.session_state.rooms
    room_ids = list(rooms.keys())
    room_labels = [rooms[rid]["name"] for rid in room_ids]
    current_index = room_ids.index(st.session_state.active_room)

    selected_label = st.radio(
        "Active room",
        options=room_labels,
        index=current_index,
        label_visibility="collapsed",
    )
    selected_id = room_ids[room_labels.index(selected_label)]
    if selected_id != st.session_state.active_room:
        st.session_state.active_room = selected_id
        st.session_state.histories.setdefault(selected_id, load_history(selected_id))
        st.session_state.ingested.setdefault(selected_id, set())
        st.rerun()

    with st.form("new_room_form", clear_on_submit=True):
        new_room_name = st.text_input("New room name", placeholder="e.g. Math Homework")
        if st.form_submit_button("â Create room", use_container_width=True):
            if new_room_name.strip():
                new_id = create_room(new_room_name)
                st.session_state.rooms = load_rooms_index()
                st.session_state.active_room = new_id
                st.session_state.histories[new_id] = []
                st.session_state.ingested[new_id] = set()
                st.rerun()
            else:
                st.warning("Give the room a name first.")

    active_id = st.session_state.active_room
    active_meta = rooms[active_id]

    st.divider()
    st.subheader("Room memory")
    try:
        stored_chunks = get_collection(active_id).count()
    except Exception:
        stored_chunks = 0
    st.metric("Indexed chunks", stored_chunks)

    files = active_meta.get("files", [])
    if files:
        st.caption("Files in this room:")
        for f in files:
            st.write(f"â¢ {f}")
    else:
        st.caption("No documents indexed in this room yet.")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("ð§¹ Clear chat", use_container_width=True):
            st.session_state.histories[active_id] = []
            save_history(active_id, [])
            st.rerun()
    with col_b:
        if st.button("ðï¸ Delete room", use_container_width=True, disabled=len(room_ids) <= 1):
            delete_room(active_id)
            st.session_state.histories.pop(active_id, None)
            st.session_state.ingested.pop(active_id, None)
            st.session_state.rooms = load_rooms_index()
            st.session_state.active_room = next(iter(st.session_state.rooms))
            st.rerun()

    st.divider()
    st.caption(f"Model: `{MODEL_NAME}`")
    st.caption(f"Storage: `{BASE_DIR}`")
    st.caption(f"Session: `{st.session_state.session_id[:8]}`")


# --------------------------------------------------------------------------- #
# Main panel
# --------------------------------------------------------------------------- #

active_id = st.session_state.active_room
active_meta = st.session_state.rooms[active_id]
history: List[Dict[str, Any]] = st.session_state.histories[active_id]

st.header(active_meta["name"])
st.caption(
    "Private, offline household intelligence Â· isolated memory per chat room Â· "
    "GPU inference on the RTX 5070 Ti Â· CPU-verified arithmetic"
)

upload_col, preview_col = st.columns([2, 1])

with upload_col:
    uploads = st.file_uploader(
        "Add documents (.txt, .pdf) or images (.png, .jpg, .jpeg) to this room",
        type=["txt", "pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key=f"uploader_{active_id}",
    )

pending_images: List[bytes] = []
image_previews: List[Tuple[str, bytes]] = []

if uploads:
    for uploaded in uploads:
        raw = uploaded.getvalue()
        suffix = Path(uploaded.name).suffix.lower()
        signature = f"{uploaded.name}:{len(raw)}"

        if suffix in (".png", ".jpg", ".jpeg"):
            try:
                image = Image.open(io.BytesIO(raw))
                image.load()
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                clean_bytes = buffer.getvalue()
                pending_images.append(clean_bytes)
                image_previews.append((uploaded.name, clean_bytes))
            except Exception as exc:
                st.error(f"Could not read image {uploaded.name}: {exc}")
        else:
            if signature in st.session_state.ingested[active_id]:
                continue
            with st.spinner(f"Vectorizing {uploaded.name} into this room's memory..."):
                count, message = ingest_document(active_id, uploaded.name, raw)
            st.session_state.ingested[active_id].add(signature)
            st.session_state.rooms = load_rooms_index()
            (st.success if count else st.warning)(message)

with preview_col:
    if image_previews:
        st.caption("Attached to your next message")
        for name, data in image_previews:
            st.image(data, caption=name, use_container_width=True)

st.divider()

for entry in history:
    with st.chat_message(entry["role"]):
        st.markdown(entry["content"])
        if entry.get("images"):
            cols = st.columns(min(len(entry["images"]), 3))
            for col, path in zip(cols, entry["images"]):
                if Path(path).exists():
                    col.image(path, use_container_width=True)


def persist_image(room_id: str, data: bytes) -> str:
    folder = UPLOADS_DIR / room_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"img_{uuid.uuid4().hex[:10]}.png"
    path.write_bytes(data)
    return str(path)


prompt = st.chat_input("Ask anything â documents, images, homework, taxes...")

if prompt:
    stored_image_paths = [persist_image(active_id, data) for data in pending_images]

    user_entry: Dict[str, Any] = {
        "role": "user",
        "content": prompt,
        "images": stored_image_paths,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    history.append(user_entry)

    with st.chat_message("user"):
        st.markdown(prompt)
        if stored_image_paths:
            cols = st.columns(min(len(stored_image_paths), 3))
            for col, path in zip(cols, stored_image_paths):
                col.image(path, use_container_width=True)

    # 1. Deterministic CPU math interception
    math_results = run_math_interceptor(prompt)
    math_block = ""
    math_preamble = ""
    if math_results:
        lines = [f"{expr} = {value}" for expr, value in math_results]
        math_block = (
            "VERIFIED CALCULATION (computed exactly on the local CPU, treat as truth):\n"
            + "\n".join(lines)
        )
        math_preamble = "**ð§® Verified calculation (local CPU)**\n\n" + "\n".join(
            f"- `{expr}` = **{value}**" for expr, value in math_results
        )

    # 2. Room-scoped vector retrieval
    hits = retrieve_context(active_id, prompt)
    reference_block = build_reference_block(hits)

    # 3. Stream the model response
    with st.chat_message("assistant"):
        if math_preamble:
            st.markdown(math_preamble)
        placeholder = st.empty()
        collected = ""
        try:
            messages = build_messages(
                history=[h for h in history[:-1]],
                user_text=prompt,
                reference_block=reference_block,
                math_block=math_block,
                image_bytes=pending_images or None,
            )
            for token in stream_ollama(messages):
                collected += token
                placeholder.markdown(collected + "â")
                time.sleep(0.005)
            placeholder.markdown(collected if collected else "_No response returned._")
        except Exception as exc:
            collected = (
                f"â ï¸ Could not reach the local model at {OLLAMA_HOST}.\n\n"
                f"`{exc}`\n\nMake sure Ollama is running and `{MODEL_NAME}` is pulled."
            )
            placeholder.markdown(collected)

        if hits:
            with st.expander(f"ð Local memory used ({len(hits)} passages)"):
                for i, hit in enumerate(hits, start=1):
                    source = hit["meta"].get("source", "memory")
                    st.markdown(f"**[{i}] {source}**")
                    st.caption(hit["text"][:800])

    final_content = f"{math_preamble}\n\n{collected}".strip() if math_preamble else collected
    history.append(
        {
            "role": "assistant",
            "content": final_content,
            "images": [],
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
    )

    st.session_state.histories[active_id] = history
    save_history(active_id, history)
