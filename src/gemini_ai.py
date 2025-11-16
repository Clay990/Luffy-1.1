import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

LUFFY_SYSTEM_PROMPT = """
You are Monkey D. Luffy, captain of the Straw Hat Pirates and future King of the Pirates.

Core personality:
- Cheerful, honest, reckless, simple-minded, emotional.
- Cries easily but recovers fast.
- Fiercely loyal to your crew and friends.
- Loves freedom more than anything.
- Hates rules, overthinking, and boring stuff.
- Acts on instinct; punches problems instead of explaining them.
- Laugh: "Shishishi!"

Story traits:
- You ate the Gomu Gomu no Mi (Nika). Your body is rubber.
- You can stretch, fight creatively, and transform using Gear 2, 3, 4, and Gear 5.
- You’ve lost Ace, saved your crew, trained with Rayleigh, and fought emperors.
- You’ve met Shanks, Jinbe, Law, Kid, and many strong enemies.
- You dream of finding the One Piece and reaching Laugh Tale.
- You believe anyone can become your friend unless they hurt your nakama.

Speaking style:
- Keep all replies short (10–20 words max).
- NEVER use asterisks, actions, or stage directions (no *stretches cheek*, *smiles*).
- Natural Luffy: mention meat only when it fits, not every message.
- Speak exactly like anime Luffy: pure dialogue, loud, simple, emotional.
- Be natural: no fancy vocabulary, no narration, no descriptions.
- When confused, say something goofy or clueless, not roleplay actions.
- Treat users as nakama on your ship.
- Never break character or admit you're a bot.

Behavior realism:
- Sometimes reference real Luffy habits: 
  - Zoro gets lost
  - Sanji cooks
  - Nami hits you for being dumb
  - Usopp lies
  - Chopper gets shy
  - Frankie says “SUPER!”
  - Brook says “Yohoho!”
- Occasionally mention past adventures naturally (Marineford, Sky Island, Dressrosa, Whole Cake, Wano).
- Never give long explanations; Luffy hates explanations.
- Show excitement about fights, food, adventures, and dreams.
"""

generation_config = {
    "temperature": 0.9,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2048,
}

safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

async def get_recruit_description(character_name):
    """
    Generates an excited or confused reaction from Luffy about recruiting a character.
    """
    recruit_model = genai.GenerativeModel('gemini-2.0-flash-lite')
    prompt = f"You are Luffy. A new crewmate, {character_name}, just joined. Give your immediate, one-sentence reaction. Be excited or confused depending on who it is. No extra narration."
    try:
        response = await recruit_model.generate_content_async(prompt)
        return response.text
    except Exception as e:
        print(f"Error calling Recruit API: {e}")
        return f"Whoa, we got {character_name}! Are they strong? Shishishi!"

async def get_adventure_description(scenario, success):
    """
    Generates a chaotic, in-character description of an adventure's outcome.
    """
    adventure_model = genai.GenerativeModel('gemini-2.0-flash-lite')
    prompt = f"Describe this One Piece adventure result in 1 short sentence as Luffy. Be chaotic. Example: 'We beat up the Marines and stole their lunch! Shishishi!'.\n\nScenario: {scenario}\nResult: {'Win' if success else 'Loss'}"
    try:
        response = await adventure_model.generate_content_async(prompt)
        return response.text
    except Exception as e:
        print(f"Error calling Adventure API: {e}")
        return "I'm not sure what happened, but it was an adventure! Shishishi!"

async def get_private_adventure_description(scenario, success):
    """
    Generates a more unique and rewarding chaotic, in-character description of a private adventure's outcome.
    """
    private_adventure_model = genai.GenerativeModel('gemini-2.0-flash-lite')
    prompt = f"Describe this special One Piece private adventure result in 2-3 short, excited sentences as Luffy. Make it sound more epic and rewarding than a regular adventure. Example: 'WHOA! We found a giant treasure chest full of meat and berries! Shishishi! Best adventure EVER!'.\n\nScenario: {scenario}\nResult: {'Win' if success else 'Loss'}"
    try:
        response = await private_adventure_model.generate_content_async(prompt)
        return response.text
    except Exception as e:
        print(f"Error calling Private Adventure API: {e}")
        return "This private adventure was SUPER! Shishishi!"

import time
import pickle
from src.firebase_utils import db

model = genai.GenerativeModel(model_name="gemini-2.5-flash",
                              generation_config=generation_config,
                              system_instruction=LUFFY_SYSTEM_PROMPT,
                              safety_settings=safety_settings)

async def is_interesting_to_luffy(message_buffer):
    """
    Uses a low-cost model to check if a conversation is interesting to Luffy.
    """
    judge_model = genai.GenerativeModel('gemini-2.0-flash-lite')
    prompt = "Is this conversation interesting to Luffy (food, adventure, one piece, treasure, etc)? Reply YES or NO.\n\n" + "\n".join(message_buffer)
    try:
        response = await judge_model.generate_content_async(prompt)
        return "YES" in response.text.upper()
    except Exception as e:
        print(f"Error calling The Judge API: {e}")
        return False

def get_luffy_response(user_id, conversation_history):
    """
    Generates a response in the persona of Monkey D. Luffy, maintaining chat history in Firestore.
    """
    chat_session_ref = db.collection('chat_sessions').document(str(user_id))
    chat_session_doc = chat_session_ref.get()

    history = []
    if chat_session_doc.exists:
        history_data = chat_session_doc.to_dict().get('history', [])
        # Convert the list of dicts back to a list of Content objects
        for item in history_data:
            role = item['role']
            parts = [part['text'] for part in item['parts']]
            history.append({'role': role, 'parts': parts})

    chat = model.start_chat(history=history)

    # Limit chat history to the last 10 messages
    if len(chat.history) > 20:
        chat.history = chat.history[-20:]
    
    try:
        response = chat.send_message(f"Conversation Context:\n{conversation_history}")

        # Convert the chat history to a JSON-serializable format
        serializable_history = []
        for content in chat.history:
            parts = [{'text': part.text} for part in content.parts]
            serializable_history.append({'role': content.role, 'parts': parts})

        chat_session_ref.set({
            'history': serializable_history,
            'last_used': time.time()
        })
        return response.text
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        raise