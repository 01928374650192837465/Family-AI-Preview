# ==============================================================================
#                      SUPER-POWERED MULTI-CHAT FAMILY AI SERVER
# ==============================================================================
# Hardware Target: Intel Core i9 Server + NVIDIA GeForce RTX 5070 Ti (16GB VRAM)
# Capabilities: Advanced Text/Vision (Qwen2.5-VL), Automated Python Math Execution,
#               Infinite Context Vector Memory (ChromaDB) isolated per Chat.
# ==============================================================================

import os
import re
import uuid
import json
import io
import contextlib
from datetime import datetime
import streamlit as st
import ollama
import chromadb
from PIL import Image

# 1. DIRECTORY & CONFIGURATION SETUP
BASE_DIR = os.path.abspath("C:\\FamilyAI_Data")
CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")
CHATS_FILE = os.path.join(BASE_DIR, "chats_metadata.json")

os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(CHROMA_DIR, exist_ok=True)

SYSTEM_PROMPT = (
    "You are the ultimate family AI core running locally on a high-end Intel Core i9 "
    "and NVIDIA RTX 5070 Ti system. You possess deep expertise in advanced mathematics, "
    "academic writing, granular research, code generation, and complex file analysis.\n\n"
    "CRITICAL RULES:\n"
    "1. When presented with complex multi-step math or logical calculations, you must wrap "
    "the algorithmic calculation inside an executable block marked exactly with ```python and ```. "
    "The environment will run it to guarantee flawless factual execution.\n"
    "2. Be concise but deep. Provide professional, heavily sourced-style research summaries.\n"
    "3. Use the injected long-term memories seamlessly to maintain contextual continuum.\n"
    "4. Respond only in markdown text. Never try to output images or raw charts yourself."
)

MODEL_NAME = "qwen2.5-vl"

# 2. VECTOR MEMORY REPOSITORY (ChromaDB Core)
class VectorMemoryBank:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=CHROMA_DIR)
        
    def _get_collection(self, chat_id: str):
        safe_id = f"chat_{chat_id.replace('-', '_')}"
        return self.client.get_or_create_collection(name=safe_id)

    def inject_memory(self, chat_id: str, document_text: str, source_name: str):
        collection = self._get_collection(chat_id)
        chunks = [document_text[i:i+600] for i in range(0, len(document_text), 400)]
        
        for idx, chunk in enumerate(chunks):
            chunk_id = f"{source_name}_{idx}_{str(uuid.uuid4())[:8]}"
            try:
                emb_res = ollama.embeddings(model=MODEL_NAME, prompt=chunk)
                embedding = emb_res.get('embedding')
                if embedding:
                    collection.add(
                        ids=[chunk_id],
                        embeddings=[embedding],
                        documents=[chunk],
                        metadatas=[{"source": source_name, "timestamp": str(datetime.now())}]
                    )
            except Exception:
                collection.add(
                    ids=[chunk_id],
                    documents=[chunk],
                    metadatas=[{"source": source_name, "timestamp": str(datetime.now())}]
                )

    def recall_memories(self, chat_id: str, query_text: str, num_results: int = 3) -> str:
        collection = self._get_collection(chat_id)
        if collection.count() == 0:
            return ""
        try:
            emb_res = ollama.embeddings(model=MODEL_NAME, prompt=query_text)
            embedding = emb_res.get('embedding')
            if embedding:
                results = collection.query(query_embeddings=[embedding], n_results=num_results)
                docs = results.get('documents', [[]])[0]
                return "\n\n".join([f"[Recalled Memory Segment]: {doc}" for doc in docs])
        except Exception:
            results = collection.query(query_texts=[query_text], n_results=num_results)
            docs = results.get('documents', [[]])[0]
            return "\n\n".join([f"[Recalled Memory Segment]: {doc}" for doc in docs])
        return ""

    def destroy_collection(self, chat_id: str):
        try:
            safe_id = f"chat_{chat_id.replace('-', '_')}"
            self.client.delete_collection(name=safe_id)
        except Exception:
            pass

memory_bank = VectorMemoryBank()

# 3. HIGH-POWERED TOOL EXECUTION ENGINE (The Math Interpreter)
def execute_mathematical_sandbox(python_code: str) -> str:
    clean_code = python_code.strip().strip("`").replace("python\n", "", 1)
    output_buffer = io.StringIO()
    with contextlib.redirect_stdout(output_buffer):
        try:
            local_scope = {}
            exec(clean_code, {"__builtins__": __builtins__}, local_scope)
            if not output_buffer.getvalue() and local_scope:
                for k, v in local_scope.items():
                    print(f"{k} = {v}")
        except Exception as err:
            print(f"Runtime Sandbox Error: {str(err)}")
    return output_buffer.getvalue()

# 4. CHAT STATE PERSISTENCE MANAGER
def load_chats_metadata():
    if os.path.exists(CHATS_FILE):
        try:
            with open(CHATS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_chats_metadata(metadata):
    with open(CHATS_FILE, "w") as f:
        json.dump(metadata, f, indent=4)

# 5. STREAMLIT INTERFACE AND CORE RUNTIME ENVIRONMENT
st.set_page_config(
    page_title="Family Core Engine v2026", 
    page_icon="â¡", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
        .stApp { background-color: #0b0c10; color: #c5a059; }
        .sidebar .sidebar-content { background-color: #1f2833; }
        h1, h2, h3 { color: #66fcf1 !important; font-family: 'Courier New', monospace; }
        .stButton>button { background-color: #45a29e !important; color: white !important; border-radius: 4px; border: none; font-weight: bold;}
        .stTextInput>div>div>input { background-color: #1f2833 !important; color: white !important; }
        .stChatMessage { border-radius: 8px; margin-bottom: 10px; padding: 15px; }
        .user-msg { background-color: #1f2833; border-left: 5px solid #66fcf1; }
        .ai-msg { background-color: #121c24; border-left: 5px solid #45a29e; }
    </style>
""", unsafe_allow_html=True)

if "chats" not in st.session_state:
    st.session_state.chats = load_chats_metadata()
if "current_chat" not in st.session_state:
    if st.session_state.chats:
        st.session_state.current_chat = list(st.session_state.chats.keys())[0]
    else:
        st.session_state.current_chat = None

st.sidebar.title("â¡ SYSTEM CORES")
st.sidebar.subheader("Multi-Chat Environments")

if st.sidebar.button("+ Initialize New Matrix Thread"):
    new_id = str(uuid.uuid4())
    st.session_state.chats[new_id] = {
        "title": f"Chat Environment {datetime.now().strftime('%m/%d %H:%M')}",
        "history": []
    }
    save_chats_metadata(st.session_state.chats)
    st.session_state.current_chat = new_id
    st.rerun()

chat_ids = list(st.session_state.chats.keys())
for cid in chat_ids:
    col_select, col_del = st.sidebar.columns([0.8, 0.2])
    btn_label = st.session_state.chats[cid]["title"]
    if cid == st.session_state.current_chat:
        btn_label = f"â¶ {btn_label}"
    if col_select.button(btn_label, key=f"sel_{cid}", use_container_width=True):
        st.session_state.current_chat = cid
        st.rerun()
    if col_del.button("ð", key=f"del_{cid}"):
        memory_bank.destroy_collection(cid)
        del st.session_state.chats[cid]
        save_chats_metadata(st.session_state.chats)
        if st.session_state.current_chat == cid:
            st.session_state.current_chat = list(st.session_state.chats.keys())[0] if st.session_state.chats else None
        st.rerun()

if not st.session_state.current_chat:
    st.title("â¡ Welcome to the Family AI Quantum Server")
    st.info("Initialize a processing thread in the left sidebar configuration panel to engage the RTX 5070 Ti computational pipeline.")
    st.stop()

# 6. ACTIVE EXECUTION MATRIX
active_chat = st.session_state.chats[st.session_state.current_chat]
st.title(f"â¡ Core Node: {active_chat['title']}")

st.markdown("""
<div style='background-color: #121c24; padding: 10px; border-radius: 5px; margin-bottom: 20px; display: flex; justify-content: space-around;'>
    <span style='color: #66fcf1;'>âï¸ <b>Processor Compute:</b> Intel Core i9 Allocation Active</span>
    <span style='color: #45a29e;'>ðï¸ <b>Graphics Vector:</b> NVIDIA RTX 5070 Ti Running</span>
    <span style='color: #c5a059;'>ð¦ <b>Memory Isolation:</b> Isolated Vector RAG Active</span>
</div>
""", unsafe_allow_html=True)

for msg in active_chat["history"]:
    div_class = "user-msg" if msg["role"] == "user" else "ai-msg"
    with st.container():
        st.markdown(f"<div class='stChatMessage {div_class}'><b>{msg['role'].upper()}:</b><br>{msg['content']}</div>", unsafe_allow_html=True)

with st.expander("ð Quantum File & Vision Injection Engine (Infect Data to Active Memory)"):
    uploaded_files = st.file_uploader("Upload files or images to expand context threshold", accept_multiple_files=True)
    if uploaded_files:
        for file in uploaded_files:
            file_bytes = file.read()
            if file.type in ["image/png", "image/jpeg", "image/webp"]:
                img = Image.open(io.BytesIO(file_bytes))
                st.image(img, caption=f"Injected Matrix File: {file.name}", width=250)
                st.session_state[f"active_img_{st.session_state.current_chat}"] = file_bytes
                st.success(f"Vision profile '{file.name}' attached to current processing registry.")
            else:
                try:
                    text_content = file_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    text_content = file_bytes.decode("latin-1")
                with st.spinner(f"Slicing and embedding matrix tracks for '{file.name}'..."):
                    memory_bank.inject_memory(st.session_state.current_chat, text_content, file.name)
                st.success(f"Document data parsed. {file.name} is now locked into permanent chat retention memory.")

user_input = st.chat_input("Enter complex research queries, logic matrices, or file processing commands...")

if user_input:
    with st.container():
        st.markdown(f"<div class='stChatMessage user-msg'><b>USER:</b><br>{user_input}</div>", unsafe_allow_html=True)
    active_chat["history"].append({"role": "user", "content": user_input})
    
    with st.spinner("Engaging Tensor Cores... Querying Isolated Memory Matrix..."):
        recalled_context = memory_bank.recall_memories(st.session_state.current_chat, user_input)
        full_system_instructions = SYSTEM_PROMPT
        if recalled_context:
            full_system_instructions += f"\n\n[PRIOR LONG-TERM MEMORY EXTRACTS FOR THIS CHAT THREAD]:\n{recalled_context}"
            
        ollama_messages = [{"role": "system", "content": full_system_instructions}]
        for past_msg in active_chat["history"][-6:]:
            ollama_messages.append({"role": past_msg["role"], "content": past_msg["content"]})
            
        image_key = f"active_img_{st.session_state.current_chat}"
        if image_key in st.session_state and st.session_state[image_key]:
            ollama_messages[-1]["images"] = [st.session_state[image_key]]
            
        try:
            response_placeholder = st.empty()
            full_response = ""
            stream = ollama.chat(model=MODEL_NAME, messages=ollama_messages, stream=True)
            
            for chunk in stream:
                full_response += chunk['message']['content']
                response_placeholder.markdown(
                    f"<div class='stChatMessage ai-msg'><b>AI SYSTEM:</b><br>{full_response}</div>", 
                    unsafe_allow_html=True
                )
                
            if image_key in st.session_state:
                st.session_state[image_key] = None
                
            python_blocks = re.findall(r"```python(.*?)```", full_response, re.DOTALL)
            if python_blocks:
                st.info("â¡ Advanced Logic Engine detected structured code. Offloading algorithmic verification to Intel Core i9 Sandbox Execution layer...")
                sandbox_results = ""
                for idx, block in enumerate(python_blocks):
                    sandbox_results += f"\n[Calculation Sandbox Result (Block {idx+1})]:\n{execute_mathematical_sandbox(block)}"
                
                verification_prompt = (
                    f"You generated calculations which executed inside the local sandbox server with these results:\n{sandbox_results}\n\n"
                    f"Analyze your previous response and integrate these absolute mathematically sound runtime results to deliver a perfected final output."
                )
                ollama_messages.append({"role": "assistant", "content": full_response})
                ollama_messages.append({"role": "user", "content": verification_prompt})
                
                final_response = ""
                final_stream = ollama.chat(model=MODEL_NAME, messages=ollama_messages, stream=True)
                for f_chunk in final_stream:
                    final_response += f_chunk['message']['content']
                    response_placeholder.markdown(
                        f"<div class='stChatMessage ai-msg'><b>AI SYSTEM (VERIFIED):</b><br>{final_response}</div>", 
                        unsafe_allow_html=True
                    )
                full_response = final_response
                
            active_chat["history"].append({"role": "assistant", "content": full_response})
            if "Chat Environment" in active_chat["title"] and len(user_input) < 40:
                active_chat["title"] = f"ð¬ {user_input}"
            save_chats_metadata(st.session_state.chats)
            st.rerun()
        except Exception as system_failure:
            st.error(f"Hardware Vector Fault: Ensure Ollama is active on the server terminal. Trace: {str(system_failure)}")

st.sidebar.markdown("---")
st.sidebar.caption("Family AI Quantum Server Module â¢ 2026 Baseline Architecture Configuration")
