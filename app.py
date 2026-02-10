# app.py
from flask import Flask, request, jsonify, send_from_directory, Response
from pathlib import Path
import requests, os, json, re
import logging # Import the logging module
# hf.co/bartowski/DeepSeek-R1-Distill-Qwen-32B-abliterated-GGUF:Q8_0    f9cf21498a97    34 GB     3 weeks ago     
# qwen3:32b-q8_0                                                        a46beca077e5    35 GB     5 weeks ago     
# hf.co/unsloth/medgemma-27b-text-it-GGUF:Q8_K_XL                       2e3e7595e6be    31 GB     6 weeks ago     
# hf.co/mlabonne/gemma-3-27b-it-abliterated-GGUF:Q8_0                   2be432ad8c2e    29 GB     2 months ago    
# gemma3:latest   
# --- CONFIGURATION ---
# This will ensure logs always appear in your terminal
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

ROOT = Path("/Users/tresmith/Documents/auto-sd/stable-diffusion-webui/scripts")
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_TIMEOUT = 300  # Timeout for Ollama requests in seconds (e.g., 300 = 5 minutes)

# Updated to gemma3 as requested
EDIT_MODEL = "hf.co/mlabonne/gemma-3-27b-it-abliterated-GGUF:Q8_0"
CHAT_MODEL = "gemma3:latest"

app = Flask(__name__, static_folder="static")

# --- PROMPTS ---
EDIT_SYSTEM_TEMPLATE = """You are an expert coding assistant. Your task is to modify a file based on the user's instructions.
The active file is {file_name}.

You MUST follow these rules:
1.  You will output one or more edit blocks to accomplish the user's goal.
2.  Each edit block starts with `<<<<<<< SEARCH` and ends with `>>>>>>> REPLACE`.
3.  The code between `<<<<<<< SEARCH` and `=======` is the code to find in the original file.
4.  The code between `=======` and `>>>>>>> REPLACE` is the new code that should replace the SEARCH block.
5.  **CRITICAL**: The content of your SEARCH block must be a direct, contiguous, verbatim copy-paste from the file. Do NOT invent code, do not paraphrase, and do not combine context from different parts of the file. The SEARCH block must exist in the file exactly as you provide it.
6.  To add code, create a SEARCH block with a line of context, then in the REPLACE block, include the context line and the new code below it.
7.  To delete code, create a SEARCH block with the code to be deleted, and leave the REPLACE block empty (i.e., `=======` followed immediately by `>>>>>>> REPLACE`).
8.  The edit blocks will be applied sequentially. This means the file content changes after each block is applied.

Example for replacing code:
<<<<<<< SEARCH
const port = 3000;
=======
const port = 8080;
>>>>>>> REPLACE

Example for adding code:
<<<<<<< SEARCH
function main() {{
=======
function main() {{
    console.log("Starting up...");
>>>>>>> REPLACE

Example for deleting code:
<<<<<<< SEARCH
    // This is an obsolete comment.
=======
>>>>>>> REPLACE

Produce ONLY the edit blocks. Do not add any other commentary or explanation.
If no changes are needed, respond with an empty string.
"""

CHAT_SYSTEM = """
You are a coding assistant. The user may ask questions about the open file.
Answer in plain language. Do NOT output a diff or modify the file.
If you want to show private reasoning, wrap it in <thinking> … </thinking>.
(The UI will hide these tags from the user.)
"""

# --- UTILITY FUNCTIONS ---

def strip_thinking(text):
    """Removes <thinking>...</thinking> or <think>...</think> blocks from a string."""
    return re.sub(r'<think(ing)?>.*?</think(ing)?>', '', text, flags=re.DOTALL).strip()

# --- FLASK ROUTES ---

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/tree")
def tree():
    files = sorted(p.name for p in ROOT.iterdir() if p.is_file())
    return jsonify(files)

@app.route("/read_file")
def read_file():
    fp = ROOT / request.args["name"]
    return fp.read_text(encoding="utf-8")

@app.route("/chat", methods=["POST"])
def chat():
    body = request.json
    edit_mode = body.get("edit", False)
    
    logging.info(f"Received /chat request in {'EDIT' if edit_mode else 'CHAT'} mode.")
    
    model = EDIT_MODEL if edit_mode else CHAT_MODEL
    
    if edit_mode:
        system_prompt = EDIT_SYSTEM_TEMPLATE.format(
            file_name=body["fileName"]
        )
    else:
        system_prompt = CHAT_SYSTEM

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"File: `{body['fileName']}`\n\nInstructions: {body['prompt']}"},
        {"role": "user", "content": f"Here is the current file content:\n```\n{body['fileText']}\n```"}
    ]

    payload = {
        "model": model,
        "messages": messages,
        "stream": True, # Always stream
        "options": {"temperature": 0.1}
    }
    # For streaming, we rely on the prompt to guide the model, so format:json is not needed.

    logging.info(f"Sending payload to Ollama (model: {model})...")

    def stream_response():
        try:
            with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=OLLAMA_TIMEOUT) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line)
                            if "content" in chunk.get("message", {}):
                                yield chunk["message"]["content"]
                        except json.JSONDecodeError:
                            continue
        except requests.RequestException as e:
            yield f'Error connecting to Ollama: {e}'

    # The frontend will handle parsing the streamed text.
    return Response(stream_response(), mimetype='text/plain')


@app.route("/apply_edits", methods=["POST"])
def apply_edits():
    data = request.json
    if not data.get("edits"):
        return "No edits to apply", 200

    current_text = data["oldText"]
    fileName = data["fileName"]
    edits = data["edits"]

    logging.info(f"Applying {len(edits)} edits to {fileName}")
    logging.debug(f"--- INITIAL CONTENT for {fileName} ---\n{current_text}\n--------------------")

    for i, edit in enumerate(edits):
        search_block = edit['search']
        replace_block = edit['replace']

        logging.info(f"--- Processing Edit {i+1}/{len(edits)} ---")
        logging.debug(f"--- AI SEARCH BLOCK ---\n{search_block}\n-----------------------")
        logging.debug(f"--- AI REPLACE BLOCK ---\n{replace_block}\n----------------------")
        
        # Intelligent Edit Strategy: Look for Python list assignments.
        # This is robust to the AI hallucinating the *contents* of the list.
        search_match = re.match(r'^\s*(\w+)\s*=\s*\[', search_block, re.MULTILINE)
        
        if not search_match:
            logging.error(f"Edit {i+1} FAILED: The AI's search block did not start with a recognized Python list assignment (e.g., 'VAR_NAME = [').")
            logging.error(f"--- FAILED SEARCH BLOCK ---\n{search_block}\n--------------------")
            return jsonify({
                "error": "The AI provided an edit block in an unrecognized format. It must be a Python list assignment.",
                "failed_edit_index": i
            }), 400

        var_name = search_match.group(1)
        logging.info(f"Detected intelligent edit for variable: '{var_name}'")

        # Build a regex to find the entire list assignment in the current file content.
        # It looks for `VAR_NAME = [` and non-greedily matches everything until `]`.
        # This is safer for the specific structure of the target files.
        pattern = re.compile(f"^{re.escape(var_name)}\s*=\s*\[[\s\S]*?\]", re.MULTILINE)
        
        if pattern.search(current_text):
            # Replace the first occurrence of the entire variable block.
            current_text = pattern.sub(replace_block, current_text, 1)
            logging.info(f"Successfully applied intelligent edit for '{var_name}'")
            logging.debug(f"--- CONTENT AFTER EDIT {i+1} ---\n{current_text}\n--------------------------------\n")
        else:
            logging.error(f"Edit {i+1} FAILED: Could not find a list assignment for '{var_name}' in the current file.")
            logging.error(f"--- FULL FILE CONTENT AT TIME OF FAILURE ---\n{current_text}\n-------------------------------------------")
            return jsonify({
                "error": f"An edit for the variable '{var_name}' could not be applied because the variable was not found in the file.",
                "failed_edit_index": i
            }), 400

    (ROOT / fileName).write_text(current_text, encoding="utf-8")
    logging.info(f"Successfully applied all edits and saved the file '{fileName}'.")
    return "", 204