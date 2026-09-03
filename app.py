import streamlit as st
import time
from PIL import Image
import re

# 1. PAGE SETUP (Saves beautifully on iPad screens)
st.set_page_config(
    page_title="Family Private AI Server (Preview)",
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
    st.caption("🔒 Secured Local Sandbox Mode")

# Get data for the currently active chat room
current_chat = st.session_state.chats[st.session_state.active_chat]

# 4. MAIN USER INTERFACE
st.title(f"🏠 Family AI Hub: {st.session_state.active_chat}")
st.write("Upload images/files and type prompts below. Memory is strictly locked to this chat room.")

# Display the long-term memory archive for this specific chat
if current_chat["memory_files"]:
    with st.expander("📚 Saved Memories for this Chat"):
        for f in current_chat["memory_files"]:
            st.write(f"• {f}")

# Display past chat history
for message in current_chat["messages"]:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# 5. MULTIMODAL UPLOADER (Takes images and files)
uploaded_file = st.file_uploader("Upload an Image or Document to save to memory:", type=["png", "jpg", "jpeg", "pdf", "txt"])

if uploaded_file:
    if uploaded_file.name not in current_chat["memory_files"]:
        current_chat["memory_files"].append(uploaded_file.name)
        st.success(f"💾 Added '{uploaded_file.name}' to {st.session_state.active_chat} memory database!")
        
    # If it's an image, display a preview on your iPad
    if uploaded_file.type in ["image/png", "image/jpeg"]:
        image = Image.open(uploaded_file)
        st.image(image, caption="Uploaded File Preview", width=250)

# 6. SMART RESPONSE ENGINE (Simulates the i9 & 5070 Ti)
user_input = st.chat_input("Ask a question, request writing, or submit a math problem...")

if user_input:
    # Display user's question immediately
    with st.chat_message("user"):
        st.write(user_input)
    current_chat["messages"].append({"role": "user", "content": user_input})
    
    # Generate the AI response
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        
        # --- SMART DETECTORS ---
        # Look for math equations (e.g., 2+2, 50*12, etc.)
        math_match = re.search(r'(\d+[\+\-\*\/]\d+)', user_input)
        
        # Decide what kind of mock answer to build based on the user's prompt
        if math_match:
            equation = math_match.group(1)
            try:
                # Simulates the Core i9 evaluating the math expression perfectly
                result = eval(equation)
                mock_text = f"⚙️ **[i9 Math Core Triggered]**\n\nI detected a math calculation in your prompt: `{equation}`. \n\nI evaluated this using the server hardware sandbox, and the mathematically absolute answer is **{result}**. Let me know if you need a step-by-step breakdown!"
            except:
                mock_text = "I found a math equation but encountered a formatting error trying to solve it."
                
        elif "write" in user_input.lower() or "essay" in user_input.lower() or "research" in user_input.lower():
            mock_text = f"📝 **[Writing & Research Core Triggered]**\n\nHere is an advanced research draft answering: *'{user_input}'*.\n\nBased on localized datasets, this topic requires deep analysis. \n\n1. **Introduction**: Expanding on the primary core concepts.\n2. **Historical Context**: Tracking patterns across data points.\n3. **Conclusion**: Summary of findings. \n\nThis paper has been logged to the filesystem archives."
            
        elif current_chat["memory_files"]:
            # If a file was uploaded, the AI acknowledges its memory
            last_file = current_chat["memory_files"][-1]
            mock_text = f"🧠 **[Vector DB Memory Retrieval Triggered]**\n\nI searched the isolated memory bank for **{st.session_state.active_chat}**.\n\nI found the file you uploaded: `{last_file}`. Based on that document context, here is the text summary answering your question about: *'{user_input}'*."
            
        else:
            # Default generic response
            mock_text = f"✨ **[Standard Local Text Core Triggered]**\n\nThis is a real-time streamed response simulating your **NVIDIA RTX 5070 Ti** core layout.\n\nYou asked: '{user_input}'. Your home server will process this locally at roughly 85 tokens per second with total data privacy."

        # Simulate text streaming out word-by-word like ChatGPT
        for word in mock_text.split(" "):
            full_response += word + " "
            time.sleep(0.06)  # Speeds up the typing animation
            response_placeholder.markdown(full_response + "▌")
            
        response_placeholder.markdown(full_response)
        
    # Commit assistant response to the isolated chat history
    current_chat["messages"].append({"role": "assistant", "content": full_response})
