#!/usr/bin/env python3
"""
Telegram MTProto StringSession Generator Helper
Use this script to generate a TELEGRAM_SESSION_STRING for your .env file.
Requirements: pip install telethon
"""

import sys
import asyncio

try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
except ImportError:
    print("Error: Telethon is required to generate a session string.")
    print("Please install it by running: pip install telethon")
    sys.exit(1)


async def main():
    print("=" * 60)
    print(" Telegram MTProto StringSession Generator")
    print("=" * 60)
    print("1. Log in to https://my.telegram.org")
    print("2. Navigate to 'API development tools'")
    print("3. Obtain your api_id (integer) and api_hash (string)\n")

    api_id_input = input("Enter your Telegram API_ID: ").strip()
    if not api_id_input.isdigit():
        print("Error: API_ID must be an integer.")
        return
    api_id = int(api_id_input)

    api_hash = input("Enter your Telegram API_HASH: ").strip()
    if not api_hash:
        print("Error: API_HASH cannot be empty.")
        return

    print("\nConnecting to Telegram... (You will receive an official Telegram login code)")
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start()

    session_str = client.session.save()
    me = await client.get_me()
    await client.disconnect()

    print("\n" + "=" * 60)
    print(f" SUCCESS! Authenticated as: {me.first_name} (@{me.username or me.id})")
    print("=" * 60)
    print("\nCopy the session string below into your .env file as TELEGRAM_SESSION_STRING:\n")
    print("-" * 60)
    print(session_str)
    print("-" * 60)
    print("\nKeep this string strictly confidential! Anyone with this string can access this Telegram session.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAborted by user.")
