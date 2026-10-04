"""Optional outbound notifications (Telegram + generic webhook). Runs in its own thread; never blocks cameras."""
import logging
import queue
import threading

import httpx

log = logging.getLogger("safetycheck.notify")
KIND_FA = {"no_helmet": "بدون کلاه ایمنی", "no_vest": "بدون لباس کار/جلیقه", "no_both": "بدون کلاه و لباس کار"}


class Notifier:
    def __init__(self, settings):
        self.settings = settings
        self.q: queue.Queue = queue.Queue(maxsize=100)
        threading.Thread(target=self._loop, daemon=True, name="notifier").start()

    def push(self, alarm: dict, image_path: str | None) -> None:
        try:
            self.q.put_nowait((alarm, image_path))
        except queue.Full:
            pass

    def _loop(self):
        while True:
            alarm, img = self.q.get()
            s = self.settings.all()
            if s["notify_min_severity"] == "high" and alarm["severity"] != "high":
                continue
            text = f"🚨 هشدار ایمنی\nدوربین: {alarm['camera']}\nتخلف: {KIND_FA.get(alarm['kind'], alarm['kind'])}\nشدت: {'بالا' if alarm['severity'] == 'high' else 'متوسط'}"
            try:
                if s["telegram_enabled"] and s["telegram_token"] and s["telegram_chat_id"]:
                    url = f"https://api.telegram.org/bot{s['telegram_token']}/"
                    if img:
                        with open(img, "rb") as f:
                            httpx.post(url + "sendPhoto", data={"chat_id": s["telegram_chat_id"], "caption": text},
                                       files={"photo": f}, timeout=15)
                    else:
                        httpx.post(url + "sendMessage", data={"chat_id": s["telegram_chat_id"], "text": text}, timeout=15)
                if s["webhook_url"]:
                    httpx.post(s["webhook_url"], json=alarm, timeout=10)
            except Exception as e:  # noqa: BLE001
                log.warning("notification failed: %s", type(e).__name__)
