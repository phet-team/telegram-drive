# 📦 Telegram Cloud Drive

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![Vue 3](https://img.shields.io/badge/Vue.js-3.x-4FC08D.svg?logo=vuedotjs&logoColor=white)](https://vuejs.org)
[![Docker](https://img.shields.io/badge/Docker-Supported-2496ED.svg?logo=docker&logoColor=white)](docker-compose.yml)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)

> **High-performance, self-hosted personal cloud storage backed by Telegram's unlimited MTProto infrastructure, featuring a Google Drive-parity web UI.**

---

## 🌟 Key Features

* **🎨 Google Drive UI Parity:** Complete folder tree navigation, breadcrumbs with context actions, drag-and-drop file organization, starred items, and soft-delete trash.
* **⚡ Persistent Telegram MTProto Engine:** Direct binary document streaming via Telethon with a persistent warm connection (no Bot API 50MB file size limits).
* **🧩 Chunk Size Optimization:** Tune chunk sizes (`4 MB` to `32 MB+`) directly via `.env` according to your server RAM and network speed, strictly constrained within Telegram MTProto policy (up to 2,000 MB per chunk).
* **⏩ RFC 9110 HTTP 206 Range Streaming:** Instant seeking and scrubbing for video, audio, and PDF preview without storing intermediate chunks on server disk.
* **🔒 Sharing & Permissions:** Granular Viewer/Editor roles, shareable links with optional password protection and expiration dates.
* **🔍 Global Instant Search:** Fast recursive search across folders with file path location metadata.

---

## ⚠️ Important Disclaimer

This project is **100% self-hosted open-source software**. 
* We do **NOT** operate, host, or provide a free public cloud service.
* Users must supply their own Telegram account credentials (`api_id`, `api_hash`, `session_string`) and host their own instance.
* Please abide by Telegram's [Terms of Service](https://telegram.org/tos).

---

## 🚀 Quick Start (Docker Compose)

Deploy a complete stack (PostgreSQL + Django API + Vue 3 Frontend) in under 3 minutes:

### 1. Prerequisites
* [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/)
* A Telegram Account
* `TELEGRAM_API_ID` & `TELEGRAM_API_HASH` from [my.telegram.org](https://my.telegram.org)

### 2. Generate Telegram Session String
Run the interactive helper script to obtain your `TELEGRAM_SESSION_STRING`:

```bash
# Optional: create a venv or run using your python environment
pip install telethon
python scripts/generate_session.py
```
Follow the prompt to enter your phone number and Telegram verification code. Copy the generated session string.

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Open `.env` and fill in:
* `TELEGRAM_API_ID` & `TELEGRAM_API_HASH`
* `TELEGRAM_SESSION_STRING` (from Step 2)
* `DJANGO_SECRET_KEY` & `JWT_SECRET_KEY` (generate random keys)
* `DB_PASSWORD` (set a secure database password)

### 4. Start the Application
Launch the entire stack with Docker Compose:

```bash
docker compose up -d
```

Open your browser at:
```
http://localhost:8080
```

---

## ⚙️ Environment Configuration Reference

| Variable | Description | Default |
| :--- | :--- | :--- |
| `PORT` | Host port exposed for web frontend | `8080` |
| `DJANGO_SECRET_KEY` | Django cryptographic signing key | *(Required)* |
| `JWT_SECRET_KEY` | JWT secret key (min 32 characters) | *(Required)* |
| `STORAGE_BACKEND` | Storage provider (`mtproto` or `mock`) | `mtproto` |
| `TELEGRAM_API_ID` | Telegram App API ID from my.telegram.org | *(Required)* |
| `TELEGRAM_API_HASH` | Telegram App API Hash | *(Required)* |
| `TELEGRAM_SESSION_STRING` | Telethon persistent StringSession | *(Required)* |
| `TELEGRAM_STORAGE_CHAT_ID`| Chat ID for storage (`me` for Saved Messages) | `me` |
| `DEFAULT_CHUNK_SIZE_MB` | Default upload chunk size in MB | `8` |
| `MIN_CHUNK_SIZE_MB` | Minimum allowable chunk size (min 1 MB) | `4` |
| `MAX_CHUNK_SIZE_MB` | Server ceiling for chunk size (max 2000 MB) | `32` |
| `VITE_CHUNK_SIZE_MB` | Frontend upload chunk size in MB | `8` |
| `GOOGLE_CLIENT_ID` / `VITE_GOOGLE_CLIENT_ID` | Google OAuth Client ID *(Optional)* | *(None)* |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token for Login Widget HMAC *(Optional)* | *(None)* |
| `VITE_TELEGRAM_BOT_ID` | Telegram Bot numeric ID for frontend widget *(Optional)* | *(None)* |
| `CORS_ALLOWED_ORIGINS` | Permitted CORS origins (comma-separated) | `http://localhost:8080` |

---

## 🔑 Authentication & OAuth (Optional)

The application supports traditional **Email & Password** registration and authentication by default without needing any external credentials.

Social Login / OAuth is **entirely optional**:
* **Google One Tap / Google Login:** 
  If you leave `GOOGLE_CLIENT_ID` (backend) and `VITE_GOOGLE_CLIENT_ID` (frontend) blank, Google OAuth is disabled. Users can still register and sign in with their email and password.
* **Telegram Widget Login:** 
  If you leave `TELEGRAM_BOT_TOKEN` (backend) and `VITE_TELEGRAM_BOT_ID` (frontend) blank, the Telegram login widget is disabled. 
  *(Note: This bot is strictly used for convenient web user login; files and chunks are always transmitted and stored via your personal MTProto user session).*

---

## 🧩 Chunk Size Optimization Guide

You can customize chunk sizes in `.env` based on your server resources:

* **Small VPS (512MB – 1GB RAM):** Set `DEFAULT_CHUNK_SIZE_MB=8`, `MAX_CHUNK_SIZE_MB=16`
* **Home Server / PC (4GB – 16GB RAM):** Set `DEFAULT_CHUNK_SIZE_MB=32`, `MAX_CHUNK_SIZE_MB=64`
* **Dedicated High-Speed Server:** Set `DEFAULT_CHUNK_SIZE_MB=128`, `MAX_CHUNK_SIZE_MB=512`

> **Note on Telegram Policy Limits:**
> Telegram MTProto has an absolute lower bound of **1 MB** (smaller chunks trigger `FloodWaitError` rate limits) and a hard ceiling of **2,000 MB** per chunk for standard accounts (or **4,000 MB** for Telegram Premium). The backend strictly validates and clamps chunks to stay within these bounds.

---

## 🏗️ Architecture

```
[ User Browser (Vue 3 / Pinia / Tailwind) ]
                     │  HTTP / WebSockets
                     ▼
          [ Nginx Reverse Proxy ]
                     │
          ┌──────────┴──────────┐
          │ /                   │ /api/
          ▼                     ▼
[ Static SPA Assets ]    [ Django REST API ]
                                │
               ┌────────────────┼────────────────┐
               ▼                                 ▼
      [ PostgreSQL 16 ]               [ Telegram MTProto ]
      (Metadata, Quota,              (Chunk Storage Cloud,
       Permissions, Shares)           Warm Persistent TCP)
```

---

## 📜 License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. See the [LICENSE](LICENSE) file for details.
