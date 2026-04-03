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
WAKE_WORD    = "max"   # say "hey max" or just "max" to activate

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
    print(f"Max: {text}")
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

# ── Volume control (Windows) ───────────────────────────────────────────────

def set_volume(level):
    """Set Windows volume 0-100 using PowerShell."""
    try:
        script = f"$obj = New-Object -com wscript.shell; $obj.SendKeys([char]173); " \
                 f"Add-Type -TypeDefinition 'using System.Runtime.InteropServices; public class V {{[DllImport(\"user32.dll\")] public static extern void keybd_event(byte b,byte c,int d,int e);}}'; " \
                 f"(New-Object -ComObject WScript.Shell).SendKeys([char]174)"
        # Simpler approach: use nircmd if available, else use pyautogui volume keys
        # Calculate presses needed (each press = ~2%)
        current = 50  # assume middle
        target = max(0, min(100, level))
        if target > current:
            presses = (target - current) // 2
            for _ in range(presses):
                pyautogui.press("volumeup")
                time.sleep(0.05)
        else:
            presses = (current - target) // 2
            for _ in range(presses):
                pyautogui.press("volumedown")
                time.sleep(0.05)
        return True
    except Exception as e:
        print(f"Volume error: {e}")
        return False

def extract_volume_level(text):
    """Extract volume number from text like 'set volume to 50'."""
    import re
    match = re.search(r'\b(\d+)\b', text)
    if match:
        return int(match.group(1))
    return None

# ── Groq ───────────────────────────────────────────────────────────────────
client = Groq(api_key=GROQ_API_KEY)

def build_system_prompt():
    return f"""You are Max, a voice assistant. Maximum 1 short sentence per reply.
No bullet points, no markdown, no long explanations.
Never say you are playing a song — the code handles playback.
If asked to play something with no song name, say: "Which song?"
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

def listen_once(timeout=5, phrase_limit=10):
    """Listen once and return text or None."""
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
        text = recognizer.recognize_google(audio, language="en-IN").strip()
        return text if len(text) > 1 else None
    except sr.WaitTimeoutError:
        return None
    except sr.UnknownValueError:
        return None
    except sr.RequestError as e:
        print(f"(speech error: {e})")
        return None
    except Exception as e:
        print(f"(mic error: {e})")
        time.sleep(0.5)
        return None

def wait_for_wake_word():
    """Keep listening silently until wake word is detected."""
    print(f"\n[Sleeping — say 'Hey Max' to wake me up]")
    while True:
        text = listen_once(timeout=4, phrase_limit=4)
        if text and WAKE_WORD in text.lower():
            print(f"Wake word detected: {text}")
            return

def listen():
    """Listen for a command after wake word."""
    time.sleep(0.1)
    print("\nListening... (speak now)")
    text = listen_once(timeout=5, phrase_limit=10)
    if text:
        print(f"You said: {text}")
    else:
        print("(couldn't understand)")
    return text

# ── Spotify / media shortcuts ──────────────────────────────────────────────

SPOTIFY_COMMANDS = {
    # pause variants — many words that sound like pause
    "pause"     : ("playpause", "Paused."),
    "paws"      : ("playpause", "Paused."),
    "stop"      : ("playpause", "Paused."),
    "halt"      : ("playpause", "Paused."),
    "hold"      : ("playpause", "Paused."),
    "freeze"    : ("playpause", "Paused."),
    "resume"    : ("playpause", "Resuming!"),
    "continue"  : ("playpause", "Resuming!"),
    "start"     : ("playpause", "Resuming!"),
    "next song" : ("nexttrack", "Next song!"),
    "next track": ("nexttrack", "Next song!"),
    "skip"      : ("nexttrack", "Skipping!"),
    "next"      : ("nexttrack", "Next!"),
    "previous"  : ("prevtrack", "Previous song."),
    "go back"   : ("prevtrack", "Going back."),
    "last song" : ("prevtrack", "Previous song."),
    "mute"      : ("volumemute","Muted."),
    "unmute"    : ("volumemute","Unmuted."),
}

def handle_media(text):
    text_lower = text.lower()

    # Volume set to specific level
    if any(w in text_lower for w in ["set volume", "volume to", "volume at"]):
        level = extract_volume_level(text_lower)
        if level is not None:
            set_volume(level)
            return f"Volume set to {level}."

    # Volume up/down
    if any(w in text_lower for w in ["volume up", "louder", "increase volume", "turn up"]):
        for _ in range(5):
            pyautogui.press("volumeup")
            time.sleep(0.05)
        return "Volume up!"
    if any(w in text_lower for w in ["volume down", "quieter", "decrease volume", "turn down"]):
        for _ in range(5):
            pyautogui.press("volumedown")
            time.sleep(0.05)
        return "Volume down."

    # Pause/play/skip etc
    for phrase, (key, reply) in SPOTIFY_COMMANDS.items():
        if phrase in text_lower:
            pyautogui.press(key)
            return reply

    return None

# ── YouTube Music ──────────────────────────────────────────────────────────

PLAY_TRIGGERS = ["play ", "search for ", "put on ", "i want to hear ",
                 "listen to ", "song "]

JUNK_QUERIES = {
    "it", "that", "this", "something", "anything", "music",
    "a song", "some music", "now", "again", "more", "the music",
    "yourself", "me", "please"
}

PLAY_CURRENT = ["just play", "play it", "play now", "play please", "play again"]

last_search = {"query": None}

def extract_song_query(text):
    text_lower = text.lower().strip()

    first_result_phrases = ["play the first", "first one", "first result",
                            "first video", "play first"]
    if any(p in text_lower for p in first_result_phrases):
        return "__FIRST_RESULT__"

    if any(text_lower == p or text_lower.startswith(p) for p in PLAY_CURRENT):
        return "__FIRST_RESULT__"

    for trigger in PLAY_TRIGGERS:
        if trigger in text_lower:
            query = text_lower.split(trigger, 1)[1].strip()
            for filler in ["the song called", "the song", "called",
                           "some", "a bit of", "me some", "the music", "song called"]:
                query = query.replace(filler, "").strip()
            if len(query) < 2 or query in JUNK_QUERIES:
                return None
            return query
    return None

def find_and_click_play():
    """Find the Play button by image matching at confidence 0.8 and click it."""
    pyautogui.hotkey("alt", "tab")
    time.sleep(0.8)
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
    print("Play button not found, using fallback click")
    screen_w, screen_h = pyautogui.size()
    pyautogui.click(int(screen_w * 0.38), int(screen_h * 0.50))
    return False

def open_youtube_music(query):
    """Pause current, open YouTube Music, click Play."""
    pyautogui.press("playpause")   # pause current song
    time.sleep(0.3)
    encoded = urllib.parse.quote(query)
    url = f"https://music.youtube.com/search?q={encoded}"
    webbrowser.open(url)
    last_search["query"] = query
    memory["songs_played"].append(query)
    save_memory(memory)
    print("Waiting for page to load...")
    time.sleep(3.5)
    find_and_click_play()

# ── Trailer ────────────────────────────────────────────────────────────────

last_suggested_movie = {"name": None}

def open_trailer(movie_name):
    query = urllib.parse.quote(f"{movie_name} official trailer")
    webbrowser.open(f"https://www.youtube.com/results?search_query={query}")

def check_trailer_request(text):
    return any(t in text.lower() for t in ["trailer", "watch it", "show me", "open it"])

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
    speak("Max is ready! Say Hey Max to wake me up.")

    while True:
        # Wait for wake word
        wait_for_wake_word()
        speak("Yeah?")

        # Listen for command
        user_input = listen()
        if not user_input:
            continue

        if any(w in user_input.lower() for w in ["goodbye", "bye", "quit", "exit", "shut down"]):
            speak("Goodbye!")
            break

        update_memory_from_text(user_input)

        # 1. Trailer
        if check_trailer_request(user_input) and last_suggested_movie["name"]:
            speak(f"Opening trailer for {last_suggested_movie['name']}!")
            open_trailer(last_suggested_movie["name"])
            continue

        # 2. Media controls (pause, volume etc)
        media_reply = handle_media(user_input)
        if media_reply:
            speak(media_reply)
            continue

        # 3. YouTube Music
        query = extract_song_query(user_input)
        if query == "__FIRST_RESULT__":
            speak("On it.")
            find_and_click_play()
            continue
        if query:
            speak(f"Playing {query}.")
            open_youtube_music(query)
            continue

        # 4. Groq chat
        reply = ask_groq(user_input)
        speak(reply)

if __name__ == "__main__":
    main()