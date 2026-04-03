import speech_recognition as sr
import pyttsx3
import os
import pyautogui
import webbrowser
import urllib.parse
import json
import time
import subprocess
from groq import Groq
from config import (
    GROQ_API_KEY, BASE_DIR, SPEECH_RATE,
    SPEECH_VOLUME, GROQ_MODEL, MAX_TOKENS
)

# ── Setup ──────────────────────────────────────────────────────────────────
os.makedirs(BASE_DIR, exist_ok=True)
MEMORY_FILE  = os.path.join(BASE_DIR, "memory.json")
PLAY_BTN_IMG = os.path.join(BASE_DIR, "play_btn.png")

# ── Load / save memory ─────────────────────────────────────────────────────

def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return {
        "favourite_actors": [], "favourite_directors": [],
        "favourite_genres": [], "watched_movies": [],
        "songs_played": [], "taste_notes": ""
    }

def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)

memory = load_memory()

# ── TTS ────────────────────────────────────────────────────────────────────

def speak(text):
    print(f"Assistant: {text}")
    try:
        tts = pyttsx3.init()
        tts.setProperty("rate", SPEECH_RATE)
        tts.setProperty("volume", SPEECH_VOLUME)
        tts.say(text)
        tts.runAndWait()
        tts.stop()
    except Exception as e:
        print(f"(TTS error: {e})")
    time.sleep(0.4)

# ── Groq ───────────────────────────────────────────────────────────────────
client = Groq(api_key=GROQ_API_KEY)

def build_system_prompt():
    return f"""You are a voice assistant. Maximum 1 short sentence per reply.
No bullet points, no markdown.
Never say you are playing a song — the code handles that.
If asked to play something vague with no song name, say: "Which song?"
For movies: ask mood, then say 2 movie names only.

User profile:
- Genres: {', '.join(memory['favourite_genres']) or 'unknown'}
- Recent songs: {', '.join(memory['songs_played'][-5:]) or 'none'}
- Movies watched: {', '.join(memory['watched_movies'][-10:]) or 'none'}"""

conversation_history = []

def reset_conversation():
    conversation_history.clear()
    conversation_history.append({"role": "system", "content": build_system_prompt()})

reset_conversation()

# ── Mic ────────────────────────────────────────────────────────────────────
recognizer = sr.Recognizer()
recognizer.pause_threshold = 0.8
recognizer.energy_threshold = 400
recognizer.dynamic_energy_threshold = True

def listen():
    time.sleep(0.1)
    try:
        with sr.Microphone() as source:
            print("\nListening... (speak now)")
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
        text = recognizer.recognize_google(audio, language="en-IN")
        text = text.strip()
        if len(text) < 2:
            return None
        print(f"You said: {text}")
        return text
    except sr.WaitTimeoutError:
        print("(no speech detected)")
    except sr.UnknownValueError:
        print("(couldn't understand audio)")
    except sr.RequestError as e:
        print(f"(speech service error: {e})")
    except Exception as e:
        print(f"(mic error: {e})")
        time.sleep(1)
    return None

# ── Spotify shortcuts ──────────────────────────────────────────────────────

SPOTIFY_COMMANDS = {
    "pause"         : ("playpause", "Paused."),
    "resume"        : ("playpause", "Resuming!"),
    "next song"     : ("nexttrack", "Next song!"),
    "skip"          : ("nexttrack", "Skipping!"),
    "previous song" : ("prevtrack", "Previous song!"),
    "go back"       : ("prevtrack", "Going back."),
    "volume up"     : ("volumeup",  "Volume up!"),
    "louder"        : ("volumeup",  "Volume up!"),
    "volume down"   : ("volumedown","Volume down."),
    "quieter"       : ("volumedown","Volume down."),
    "mute"          : ("volumemute","Muted."),
    "unmute"        : ("volumemute","Unmuted."),
}

def handle_spotify(text):
    text_lower = text.lower()
    for phrase, (key, reply) in SPOTIFY_COMMANDS.items():
        if phrase in text_lower:
            pyautogui.press(key)
            return reply
    return None

# ── YouTube Music auto-play ────────────────────────────────────────────────

PLAY_TRIGGERS = ["play ", "search for ", "put on ", "i want to hear ", "listen to ", "song "]

JUNK_QUERIES = {
    "it", "that", "this", "something", "anything", "music",
    "a song", "some music", "now", "again", "more", "the music",
    "it by yourself", "yourself", "me", "please"
}

# Phrases that mean "play whatever is already loaded"
PLAY_CURRENT = [
    "just play", "play it", "play now", "play please",
    "could you please play", "can you play", "please play"
]

last_search = {"query": None}

def extract_song_query(text):
    text_lower = text.lower().strip()
    first_result_phrases = [
        "play the first", "first one", "first result",
        "first video", "play first", "that first one"
    ]
    if any(p in text_lower for p in first_result_phrases):
        return "__FIRST_RESULT__"
    # "just play it" / "play it now" = click play on whatever is open
    if any(text_lower == p or text_lower.startswith(p) for p in PLAY_CURRENT):
        return "__FIRST_RESULT__"
    for trigger in PLAY_TRIGGERS:
        if trigger in text_lower:
            query = text_lower.split(trigger, 1)[1].strip()
            for filler in ["the song called", "the song", "some", "a bit of",
                           "me some", "the music", "called", "song called"]:
                query = query.replace(filler, "").strip()
            if len(query) < 3 or query in JUNK_QUERIES:
                return None
            return query
    return None

def bring_browser_to_front():
    """Bring browser to front using alt+tab."""
    pyautogui.hotkey("alt", "tab")
    time.sleep(0.8)

def find_and_click_play():
    """Find the Play button by image matching at confidence 0.8 and click it."""
    bring_browser_to_front()
    if os.path.exists(PLAY_BTN_IMG):
        for conf in [0.8, 0.7, 0.6]:
            try:
                loc = pyautogui.locateOnScreen(PLAY_BTN_IMG, confidence=conf)
                if loc:
                    center = pyautogui.center(loc)
                    print(f"Play button found at {center} (conf={conf})")
                    pyautogui.click(center)
                    return True
            except Exception:
                continue
    print("Play button not found, trying fallback click")
    screen_w, screen_h = pyautogui.size()
    pyautogui.click(int(screen_w * 0.38), int(screen_h * 0.50))
    return False

def open_youtube_music(query):
    """Pause current song, open YouTube Music search, then auto-click Play."""
    # Pause whatever is currently playing first
    pyautogui.press("playpause")
    time.sleep(0.3)

    encoded = urllib.parse.quote(query)
    url = f"https://music.youtube.com/search?q={encoded}"
    webbrowser.open(url)
    last_search["query"] = query
    memory["songs_played"].append(query)
    save_memory(memory)

    print("Waiting for page to load...")
    time.sleep(3.5)        # reduced from 5s
    find_and_click_play()

# ── Trailer ────────────────────────────────────────────────────────────────

last_suggested_movie = {"name": None}

def open_trailer(movie_name):
    query = urllib.parse.quote(f"{movie_name} official trailer")
    webbrowser.open(f"https://www.youtube.com/results?search_query={query}")

def check_trailer_request(text):
    return any(t in text.lower() for t in ["trailer", "watch it", "show me", "yes please", "open it"])

# ── Memory ─────────────────────────────────────────────────────────────────

def update_memory_from_text(text):
    text_lower = text.lower()
    for trigger in ["i've seen", "i watched", "already seen"]:
        if trigger in text_lower:
            after = text_lower.split(trigger, 1)[-1].strip().rstrip(".")
            if after and after not in memory["watched_movies"]:
                memory["watched_movies"].append(after.title())
                save_memory(memory)
            break
    genres = ["action","comedy","horror","romance","thriller","sci-fi",
              "drama","animation","documentary","fantasy","mystery"]
    for genre in genres:
        if genre in text_lower and genre not in memory["favourite_genres"]:
            if any(t in text_lower for t in ["love","like","enjoy","favourite"]):
                memory["favourite_genres"].append(genre)
                save_memory(memory)

# ── Groq chat ──────────────────────────────────────────────────────────────

def ask_groq(user_text):
    conversation_history.append({"role": "user", "content": user_text})
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=conversation_history,
        max_tokens=MAX_TOKENS,
        temperature=0.7,
    )
    reply = response.choices[0].message.content
    conversation_history.append({"role": "assistant", "content": reply})
    for word in reply.split():
        if word.istitle() and len(word) > 3:
            last_suggested_movie["name"] = word
            break
    return reply

# ── Main ───────────────────────────────────────────────────────────────────

def main():
    speak("Hey! I am your assistant. How can I help you today?")

    while True:
        user_input = listen()
        if user_input is None:
            continue

        if any(w in user_input.lower() for w in ["goodbye", "bye", "quit", "exit"]):
            speak("Goodbye! Catch you later.")
            break

        update_memory_from_text(user_input)

        # 1. Trailer
        if check_trailer_request(user_input) and last_suggested_movie["name"]:
            speak(f"Opening the trailer for {last_suggested_movie['name']}!")
            open_trailer(last_suggested_movie["name"])
            continue

        # 2. Spotify shortcuts
        spotify_reply = handle_spotify(user_input)
        if spotify_reply:
            speak(spotify_reply)
            continue

        # 3. YouTube Music
        query = extract_song_query(user_input)
        if query == "__FIRST_RESULT__":
            speak("Clicking play for you.")
            find_and_click_play()
            continue
        if query:
            speak(f"Playing {query} now.")
            open_youtube_music(query)
            continue

        # 4. Groq chat
        reply = ask_groq(user_input)
        speak(reply)

if __name__ == "__main__":
    main()