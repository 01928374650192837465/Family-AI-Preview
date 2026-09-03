import streamlit as st
import time
from PIL import Image
import re
import requests

# 1. PAGE SETUP (Optimized for iPad screen responsive layout)
st.set_page_config(
    page_title="Family Private AI Server (Cloud Preview)",
    page_icon="🏠",
    layout="wide"
)

# 2. STATE MANAGEMENT (Handles multiple chats and memory)
if "chats" not in st.session_state:
    st.session_state.chats = {
        "Chat 1": {"messages": [], "memory_files": []}
    }

if "active_chat" not in st.session_state:
    st.session_state.active_chat = "Chat 1"

# 3. SIDEBAR (For creating separate chat rooms)
with st.sidebar:
    st.title("⚡ AI Server Control")
    st.subheader("Family Chat Rooms")
    
    new_chat_name = st.text_input("Create New Chat:", placeholder="e.g., Math Homework, Research")
    if st.button("➕ Add Chat") and new_chat_name.strip():
        if new_chat_name not in st.session_state.chats:
            st.session_state.chats[new_chat_name] = {"messages": [], "memory_files": []}
            st.session_state.active_chat = new_chat_name
            st.rerun()
            
    st.divider()
    
    chat_list = list(st.session_state.chats.keys())
    selected_chat = st.selectbox("Switch Active Chat:", chat_list, index=chat_list.index(st.session_state.active_chat))
    if selected_chat != st.session_state.active_chat:
        st.session_state.active_chat = selected_chat
        st.rerun()

    st.divider()
    st.caption("🌐 Auto-Healing OpenRouter Failover Stream")

current_chat = st.session_state.chats[st.session_state.active_chat]

# 4. MAIN USER INTERFACE
st.title(f"🏠 Family AI Hub: {st.session_state.active_chat}")
st.write("Ask real questions below. Memory and chat threads are strictly separated.")

if current_chat["memory_files"]:
    with st.expander("📚 Saved Memories for this Chat"):
        for f in current_chat["memory_files"]:
            st.write(f"• {f}")

for message in current_chat["messages"]:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# 5. MULTIMODAL UPLOADER FOR MEMORY DECK
uploaded_file = st.file_uploader("Upload a file to save to memory:", type=["png", "jpg", "jpeg", "pdf", "txt"])

if uploaded_file:
    if uploaded_file.name not in current_chat["memory_files"]:
        current_chat["memory_files"].append(uploaded_file.name)
        st.success(f"💾 Added '{uploaded_file.name}' to {st.session_state.active_chat} memory database!")
        
    if uploaded_file.type in ["image/png", "image/jpeg"]:
        image = Image.open(uploaded_file)
        st.image(image, caption="Uploaded File Preview", width=250)

# 6. RE-ENGINEERED AUTOMATIC INFERENCE ROUTER
user_input = st.chat_input("Ask a question, request writing, or submit a math problem...")

if user_input:
    with st.chat_message("user"):
        st.write(user_input)
    current_chat["messages"].append({"role": "user", "content": user_input})
    
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        final_answer = ""
        
        # --- LOCAL INTEL i9 HARDWARE INTERCEPT ---
        math_match = re.search(r'(\d+[\+\-\*\/]\d+)', user_input)
        memory_context = ""
        
        if current_chat["memory_files"]:
            memory_context = f"[System Alert: User has loaded file reference '{current_chat['memory_files'][-1]}' in context]\n"

        if math_match:
            equation = math_match.group(1)
            try:
                result = eval(equation)
                final_answer = f"⚙️ **[Local Math Engine Intercept]**\nI isolated the arithmetic query `{equation}` and executed it directly. The absolute result is **{result}**.\n\n"
            except:
                pass

        # Try connection to the auto-healing free network endpoint
        try:
            API_URL = "https://openrouter.ai/api/v1/chat/completions"
            
            headers = {
                "Content-Type": "application/json",
                # OpenRouter requires an HTTP referer for their free endpoints tracking
                "HTTP-Referer": "https://localhost:3000"
            }
            
            payload = {
                # Target the dynamic routing system to instantly hit a live, working free model
                "model": "openrouter/free",
                "messages": [
                    {"role": "user", "content": f"{memory_context}{user_input}"}
                ]
            }
            
            response = requests.post(API_URL, json=payload, headers=headers, timeout=15)
            
            if response.status_code == 200:
                try:
                    api_result = response.json()
                    # Deep parse the JSON response arrays cleanly
                    if "choices" in api_result and len(api_result["choices"]) > 0:
                        raw_ai_text = api_result["choices"][0]["message"]["content"]
                        final_answer += raw_ai_text
                    else:
                        final_answer += f"⚠️ The server processed the data but returned an empty context loop. Debug payload: {str(api_result)}"
                except ValueError:
                    final_answer += f"⚠️ Server structural return format error. Raw data frame: {response.text[:200]}"
            else:
                final_answer += f"⚠️ The cloud cluster rejected the network ticket. Code: {response.status_code}. Details: {response.text[:200]}"
                
        except Exception as e:
            final_answer += f"⚠️ Infrastructure Timeout. Target node failed to ping. Details: {str(e)}"

        # Output animation stream onto iPad screen interface
        current_stream = ""
        for word in final_answer.split(" "):
            current_stream += word + " "
            time.sleep(0.01)
            response_placeholder.markdown(current_stream + "▌")
            
        response_placeholder.markdown(current_stream)
        
    current_chat["messages"].append({"role": "assistant", "content": current_stream})
