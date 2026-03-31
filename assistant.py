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
    time.sleep(0.8)   # extra pause so mic doesn't catch speaker output

# ── Groq ───────────────────────────────────────────────────────────────────
client = Groq(api_key=GROQ_API_KEY)

def build_system_prompt():
    return f"""You are a friendly voice assistant on the user's Windows laptop.
Keep answers short and natural — speaking aloud, not writing.
Maximum 2 sentences per reply. No bullet points or markdown.
You CAN play songs by opening YouTube Music and clicking play automatically.
When asked to play a song, just confirm you are playing it.

User taste profile:
- Favourite actors: {', '.join(memory['favourite_actors']) or 'unknown'}
- Favourite genres: {', '.join(memory['favourite_genres']) or 'unknown'}
- Songs recently played: {', '.join(memory['songs_played'][-10:]) or 'none'}
- Movies watched: {', '.join(memory['watched_movies'][-20:]) or 'none'}

For movie suggestions: ask 1 mood question, then suggest 2 movies. Ask about trailer after."""

conversation_history = []

def reset_conversation():
    conversation_history.clear()
    conversation_history.append({"role": "system", "content": build_system_prompt()})

reset_conversation()

# ── Mic ────────────────────────────────────────────────────────────────────
recognizer = sr.Recognizer()
recognizer.pause_threshold = 1.0

def listen():
    time.sleep(0.3)   # small gap before opening mic
    try:
        with sr.Microphone() as source:
            print("\nListening... (speak now)")
            recognizer.adjust_for_ambient_noise(source, duration=0.4)
            audio = recognizer.listen(source, timeout=6, phrase_time_limit=12)
        text = recognizer.recognize_google(audio)
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

PLAY_TRIGGERS = ["play ", "search for ", "put on ", "i want to hear ", "listen to "]

JUNK_QUERIES = {
    "it", "that", "this", "something", "anything", "music", "song",
    "a song", "some music", "now", "again", "more", "the music",
    "it by yourself", "yourself", "me", "please"
}

last_search = {"query": None}

def extract_song_query(text):
    text_lower = text.lower().strip()
    first_result_phrases = [
        "play the first", "first one", "first result",
        "first video", "play first", "that first one"
    ]
    if any(p in text_lower for p in first_result_phrases):
        return "__FIRST_RESULT__"
    for trigger in PLAY_TRIGGERS:
        if trigger in text_lower:
            query = text_lower.split(trigger, 1)[1].strip()
            for filler in ["the song", "some", "a bit of", "me some", "the music"]:
                query = query.replace(filler, "").strip()
            if len(query) < 3 or query in JUNK_QUERIES:
                return None
            return query
    return None

def bring_browser_to_front():
    """Use Windows to bring the browser window to front reliably."""
    # Click on the taskbar area where browser would be, then use alt+tab
    pyautogui.hotkey("alt", "tab")
    time.sleep(0.8)

def find_and_click_play():
    """Find the Play button using image matching, then click it."""
    bring_browser_to_front()

    if os.path.exists(PLAY_BTN_IMG):
        try:
            location = pyautogui.locateOnScreen(PLAY_BTN_IMG, confidence=0.6)
            if location:
                center = pyautogui.center(location)
                print(f"Play button found at {center}")
                pyautogui.click(center)
                return True
            else:
                print("Image not found on screen, trying lower confidence...")
                location = pyautogui.locateOnScreen(PLAY_BTN_IMG, confidence=0.4)
                if location:
                    center = pyautogui.center(location)
                    pyautogui.click(center)
                    return True
        except Exception as e:
            print(f"Image match error: {e}")

    # Fallback: click middle of screen where Play button usually appears
    print("Using click fallback at Play button area")
    screen_w, screen_h = pyautogui.size()
    # Play button is roughly at 40% from left, 50% from top
    pyautogui.click(int(screen_w * 0.40), int(screen_h * 0.50))
    return False

def open_youtube_music(query):
    """Open YouTube Music search then auto-click Play."""
    encoded = urllib.parse.quote(query)
    url = f"https://music.youtube.com/search?q={encoded}"
    webbrowser.open(url)
    last_search["query"] = query
    memory["songs_played"].append(query)
    save_memory(memory)

    print("Waiting for page to load...")
    time.sleep(5)          # wait for page to fully load
    find_and_click_play()  # click play button

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