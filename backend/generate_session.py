"""
Helper script to generate TELEGRAM_SESSION_STRING for MTProto Cloud Storage.
Run this interactively in your terminal:
    .\venv\Scripts\python.exe generate_session.py
"""
import os
import sys

# Ensure backend directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telethon.sync import TelegramClient
from telethon.sessions import StringSession

def main():
    print("=" * 60)
    print("  Telegram MTProto Session String Generator")
    print("=" * 60)
    print("This will log into your Telegram account and produce a session string.")
    print("Files will be stored securely in your 'Saved Messages'.\n")

    api_id_val = os.environ.get("TELEGRAM_API_ID", "").strip()
    if not api_id_val:
        api_id_val = input("Enter your Telegram API_ID: ").strip()

    api_hash_val = os.environ.get("TELEGRAM_API_HASH", "").strip()
    if not api_hash_val:
        api_hash_val = input("Enter your Telegram API_HASH: ").strip()

    if not api_id_val.isdigit() or not api_hash_val:
        print("[ERROR] Valid API_ID (integer) and API_HASH are required.")
        return

    api_id = int(api_id_val)
    api_hash = api_hash_val

    try:
        with TelegramClient(StringSession(), api_id, api_hash) as client:
            session_str = client.session.save()
            me = client.get_me()
            print("\n" + "=" * 60)
            print(f" SUCCESS! Logged in as: {me.first_name} (@{me.username or me.id})")
            print("=" * 60)
            print("\nCopy the TELEGRAM_SESSION_STRING below:\n")
            print("-" * 60)
            print(session_str)
            print("-" * 60 + "\n")
            
            # Save into .env automatically if it exists
            env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                if "TELEGRAM_SESSION_STRING=" in content:
                    lines = content.splitlines()
                    new_lines = []
                    for line in lines:
                        if line.startswith("TELEGRAM_SESSION_STRING="):
                            new_lines.append(f"TELEGRAM_SESSION_STRING={session_str}")
                        elif line.startswith("STORAGE_BACKEND="):
                            new_lines.append("STORAGE_BACKEND=mtproto")
                        else:
                            new_lines.append(line)
                    with open(env_path, "w", encoding="utf-8") as f:
                        f.write("\n".join(new_lines) + "\n")
                    print("--> Automatically saved to backend/.env and set STORAGE_BACKEND=mtproto")

            print("\nReady! Now use this session string in Render environment variables.\n")
    except Exception as e:
        print(f"\n[ERROR] Failed to generate session: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
