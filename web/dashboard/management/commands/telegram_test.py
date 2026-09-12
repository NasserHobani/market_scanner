"""اختبار تيليجرام مع تشخيص واضح لكل سبب فشل محتمل.

    python web/manage.py telegram_test
    python web/manage.py telegram_test --chat-id        (لاكتشاف معرّف المحادثة)
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from django.core.management.base import BaseCommand

API = "https://api.telegram.org/bot{token}/{method}"


class Command(BaseCommand):
    help = "يرسل رسالة اختبار إلى تيليجرام ويشخّص أي فشل"

    def add_arguments(self, parser):
        parser.add_argument("--chat-id", action="store_true",
                            help="اعرض معرّفات المحادثات التي راسلت البوت")
        parser.add_argument("--text", default=None, help="نص مخصص")

    def handle(self, *args, **opts):
        token = os.getenv("TELEGRAM_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

        self.stdout.write("─" * 52)
        self.stdout.write("فحص إعدادات تيليجرام")
        self.stdout.write("─" * 52)

        from django.conf import settings
        env_file = getattr(settings, "ENV_FILE", None)
        if env_file is not None:
            exists = env_file.exists()
            self.stdout.write(f"  ملف .env: {'موجود' if exists else 'غير موجود'} — {env_file}")
            if exists:
                self.stdout.write(f"  حُمّل منه: {getattr(settings, 'ENV_LOADED', 0)} متغير")

        if not token:
            return self._fail(
                "TELEGRAM_TOKEN غير مضبوط",
                ["أنشئ بوتاً بمراسلة @BotFather على تيليجرام",
                 "أرسل /newbot واتبع الخطوات",
                 "انسخ التوكن وضعه في .env:",
                 "    TELEGRAM_TOKEN=123456:ABC-DEF..."])

        # فحص الصيغة قبل الشبكة: «Not Found» من تيليجرام لا يشرح أن
        # التوكن ناقص، وأشيع خطأ هو نسخ ما بعد النقطتين وحده
        problem = self._token_problem(token)
        if problem:
            return self._fail(problem, [
                "الصيغة الصحيحة:  8123456789:AAGcgVxI-oPqRs…",
                "                 └─ معرّف البوت ─┘ └─ النص السرّي ─┘",
                "افتح محادثة @BotFather وأرسل  /mybots",
                "اختر بوتك ← API Token ← انسخ *السطر كاملاً*",
                "التوكن يبدأ برقم دائماً، وفيه نقطتان رأسيتان",
            ])

        bot_id = token.split(":", 1)[0]
        masked = f"{bot_id}:{token.split(':', 1)[1][:6]}…{token[-4:]}"
        self.stdout.write(f"  التوكن: {masked}")

        # ١) هل التوكن صحيح؟
        ok, data, err = self._call(token, "getMe", {})
        if not ok:
            return self._fail(f"التوكن مرفوض: {err}",
                              ["تحقّق من نسخ التوكن كاملاً بلا مسافات",
                               "أو أنشئ توكناً جديداً من @BotFather"])
        bot = data.get("result", {})
        self.stdout.write(self.style.SUCCESS(
            f"  ✓ البوت: @{bot.get('username')} ({bot.get('first_name')})"))

        # ٢) اكتشاف معرّف المحادثة
        if opts["chat_id"] or not chat_id:
            ok, data, err = self._call(token, "getUpdates", {"limit": 20})
            chats = {}
            if ok:
                for upd in data.get("result", []):
                    msg = upd.get("message") or upd.get("channel_post") or {}
                    chat = msg.get("chat") or {}
                    sender = msg.get("from") or {}
                    if chat.get("id") and not sender.get("is_bot"):
                        kind = {"private": "خاص", "group": "مجموعة",
                                "supergroup": "مجموعة", "channel": "قناة"}.get(
                                    chat.get("type", ""), chat.get("type", ""))
                        name = (chat.get("title") or chat.get("username")
                                or chat.get("first_name") or "—")
                        chats[chat["id"]] = f"{name} · {kind}"
            if chats:
                self.stdout.write("\n  المحادثات المتاحة:")
                for cid, name in chats.items():
                    self.stdout.write(f"    TELEGRAM_CHAT_ID={cid}   ({name})")
            else:
                self.stdout.write(self.style.WARNING(
                    "\n  لا محادثات — أرسل أي رسالة للبوت أولاً ثم أعد الأمر"))
            if opts["chat_id"]:
                return

        if not chat_id:
            return self._fail(
                "TELEGRAM_CHAT_ID غير مضبوط",
                ["أرسل /start للبوت من حسابك",
                 "ثم:  python web/manage.py telegram_test --chat-id",
                 "وانسخ الرقم إلى .env"])

        # خطأ شائع ويصعب تفسيره من رسالة تيليجرام: وضع معرّف البوت
        # بدل معرّف الحساب. الرقمان متطابقان لأن معرّف البوت هو صدر التوكن.
        if chat_id == bot_id:
            return self._fail(
                "TELEGRAM_CHAT_ID هو معرّف البوت نفسه — والبوت لا يراسل نفسه",
                ["المطلوب معرّف *حسابك أنت*، وهو رقم مختلف تماماً",
                 f"لاحظ أن {chat_id} هو نفسه صدر التوكن",
                 "",
                 "الخطوات:",
                 f"  ١) افتح تيليجرام وابحث عن  @{bot.get('username')}",
                 "  ٢) اضغط Start أو أرسل أي رسالة",
                 "  ٣) شغّل:  python web/manage.py telegram_test --chat-id",
                 "  ٤) انسخ الرقم الذي يظهر إلى .env"])

        self.stdout.write(f"  معرّف المحادثة: {chat_id}")

        # ٣) الإرسال الفعلي
        text = opts["text"] or self._sample()
        ok, data, err = self._call(token, "sendMessage", {
            "chat_id": chat_id, "text": text, "parse_mode": "Markdown",
            "disable_web_page_preview": "true",
        })
        if not ok:
            low = err.lower()
            hints = []
            if "can't send messages to the bot" in low or "cant send messages to the bot" in low:
                hints = ["المعرّف يشير إلى بوت لا إلى حساب بشري",
                         "استخدم --chat-id للحصول على معرّفك الصحيح"]
            elif "chat not found" in low:
                hints = ["المعرّف خاطئ أو لم تراسل البوت بعد",
                         f"أرسل /start إلى @{bot.get('username')} ثم استخدم --chat-id"]
            elif "bot was blocked" in low:
                hints = ["أنت حاظر البوت — ألغِ الحظر من محادثته"]
            elif "not enough rights" in low or "need administrator" in low:
                hints = ["البوت في مجموعة بلا صلاحية إرسال — اجعله مشرفاً"]
            else:
                hints = ["تأكد أنك أرسلت /start للبوت من هذه المحادثة"]
            return self._fail(f"تعذّر الإرسال: {err}", hints)

        self.stdout.write("─" * 52)
        self.stdout.write(self.style.SUCCESS("  ✓ أُرسلت رسالة الاختبار بنجاح"))
        self.stdout.write("  افتح تيليجرام — يجب أن تراها الآن")
        self.stdout.write("─" * 52)

    # ────────────────────────────────────────────────

    def _call(self, token: str, method: str, params: dict):
        url = API.format(token=token, method=method)
        data = urllib.parse.urlencode(params).encode() if params else None
        try:
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode())
            if not payload.get("ok"):
                return False, payload, payload.get("description", "رفض غير معروف")
            return True, payload, ""
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read().decode())
                return False, body, body.get("description", f"HTTP {exc.code}")
            except Exception:  # noqa: BLE001
                return False, {}, f"HTTP {exc.code}"
        except urllib.error.URLError as exc:
            return False, {}, f"تعذّر الوصول: {exc.reason}"
        except Exception as exc:  # noqa: BLE001
            return False, {}, str(exc)[:120]

    @staticmethod
    def _token_problem(token: str) -> str:
        """يعيد وصف الخلل في صيغة التوكن، أو نصاً فارغاً إن بدا سليماً."""
        if ":" not in token:
            if token[:1].isalpha():
                return ("التوكن ناقص — يبدو أنك نسخت ما بعد النقطتين فقط. "
                        "ينقصه معرّف البوت الرقمي والنقطتان في البداية")
            return "التوكن لا يحتوي على النقطتين ( : ) الفاصلتين"

        head, _, tail = token.partition(":")
        if not head.isdigit():
            return f"ما قبل النقطتين يجب أن يكون رقماً، وهو الآن: {head[:16]}"
        if len(head) < 6:
            return f"معرّف البوت قصير جداً ({len(head)} أرقام) — يُتوقّع 8 إلى 10"
        if len(tail) < 30:
            return f"النص السرّي قصير ({len(tail)} حرفاً) — يُتوقّع نحو 35"
        if any(ch.isspace() for ch in token):
            return "التوكن يحتوي مسافة أو سطراً جديداً — احذفها"
        return ""

    def _fail(self, reason: str, hints: list[str]) -> None:
        self.stdout.write("─" * 52)
        self.stderr.write(f"  ✗ {reason}")
        if hints:
            self.stdout.write("\n  الحل:")
            for h in hints:
                self.stdout.write(f"    · {h}")
        self.stdout.write("─" * 52)

    @staticmethod
    def _sample() -> str:
        return "\n".join([
            "✅ *اختبار ماسح الأسواق*",
            "",
            "الاتصال يعمل. هكذا ستصلك التنبيهات:",
            "",
            "🎯 *وصل سعر الدخول* — ZECUSDT",
            "السعر الآن: *471.3*",
            "الوقف: 449.9 · الهدف: 507",
            "العائد/المخاطرة: 1:1.67 · التصنيف: A",
            "",
            "_راجع الشارت قبل التنفيذ._",
        ])
