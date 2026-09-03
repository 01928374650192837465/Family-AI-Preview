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
    
    # Create a new, isolated chat room
    new_chat_name = st.text_input("Create New Chat:", placeholder="e.g., Math Homework, Research")
    if st.button("➕ Add Chat") and new_chat_name.strip():
        if new_chat_name not in st.session_state.chats:
            st.session_state.chats[new_chat_name] = {"messages": [], "memory_files": []}
            st.session_state.active_chat = new_chat_name
            st.rerun()
            
    st.divider()
    
    # Dropdown to switch between the isolated chats
    chat_list = list(st.session_state.chats.keys())
    selected_chat = st.selectbox("Switch Active Chat:", chat_list, index=chat_list.index(st.session_state.active_chat))
    if selected_chat != st.session_state.active_chat:
        st.session_state.active_chat = selected_chat
        st.rerun()

    st.divider()
    st.caption("🌐 High-Availability OpenRouter Sandbox")

# Get data for the currently active chat room
current_chat = st.session_state.chats[st.session_state.active_chat]

# 4. MAIN USER INTERFACE
st.title(f"🏠 Family AI Hub: {st.session_state.active_chat}")
st.write("Ask real questions below. Memory and chat threads are strictly separated.")

# Display the long-term memory archive for this specific chat
if current_chat["memory_files"]:
    with st.expander("📚 Saved Memories for this Chat"):
        for f in current_chat["memory_files"]:
            st.write(f"• {f}")

# Display past chat history
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

# 6. INTEGRATED REAL-RESPONSE AI CORE (OpenRouter High-Availability Network)
user_input = st.chat_input("Ask a question, request writing, or submit a math problem...")

if user_input:
    # Display user's question immediately
    with st.chat_message("user"):
        st.write(user_input)
    current_chat["messages"].append({"role": "user", "content": user_input})
    
    # Process and build the AI response
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        final_answer = ""
        
        # --- PRE-PROCESSING INTERCEPTORS ---
        math_match = re.search(r'(\d+[\+\-\*\/]\d+)', user_input)
        memory_context = ""
        
        if current_chat["memory_files"]:
            memory_context = f"[System Context: The user has loaded a file named '{current_chat['memory_files'][-1]}' into memory.]\n"

        # Math engine execution loop (Intel Core i9 Simulation)
        if math_match:
            equation = math_match.group(1)
            try:
                result = eval(equation)
                final_answer = f"⚙️ **[Local Math Engine Intercept]**\nI isolated the arithmetic query `{equation}` and executed it directly. The absolute result is **{result}**.\n\n"
            except:
                pass

        # Call the live high-speed OpenRouter API
        try:
            # Targets OpenRouter's high-speed, free-tier distributed cluster
            API_URL = "https://openrouter.ai"
            
            headers = {
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "meta-llama/llama-3-8b-instruct:free",
                "messages": [
                    {"role": "user", "content": f"{memory_context}{user_input}"}
                ]
            }
            
            response = requests.post(API_URL, json=payload, headers=headers, timeout=15)
            
            if response.status_code == 200:
                api_result = response.json()
                raw_ai_text = api_result["choices"][0]["message"]["content"]
                final_answer += raw_ai_text
            else:
                final_answer += f"⚠️ Server communication delay. Error Code: {response.status_code}. Please try submitting again!"
                
        except Exception as e:
            final_answer += f"⚠️ Network Connection Error: Could not reach the cluster. Details: {str(e)}"

        # Print the final result text smoothly word-by-word like ChatGPT
        current_stream = ""
        for word in final_answer.split(" "):
            current_stream += word + " "
            time.sleep(0.02)
            response_placeholder.markdown(current_stream + "▌")
            
        response_placeholder.markdown(current_stream)
        
    # Commit assistant response to the isolated chat history array
    current_chat["messages"].append({"role": "assistant", "content": current_stream})
