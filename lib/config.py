from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "NikkeWitchcraft"
APP_VERSION = "1.06"
APP_TITLE = f"{APP_NAME} v{APP_VERSION}"


@dataclass
class Settings:
    # delays
    click1_hold_ms: int = 225
    click1_gap_ms: int = 25
    click2_hold_ms: int = 240
    click2_gap_ms: int = 40
    click3_hold_ms: int = 240
    click3_gap_ms: int = 40
    key_spam_delay_ms: int = 34

    # keys
    key_spam_d: str = "F13"
    key_spam_s: str = "F14"
    key_spam_a: str = "F15"
    key_click1: str = "F17"
    key_click2: str = "F18"
    key_click3: str = "F19"
    key_jitter: str = "F20"

    # enable
    is_spam_d_enabled: bool = True
    is_spam_s_enabled: bool = True
    is_spam_a_enabled: bool = True
    is_click1_enabled: bool = True
    is_click2_enabled: bool = True
    is_click3_enabled: bool = True
    is_jitter_enabled: bool = True

    # jitter toggle
    jitter_z: bool = True
    jitter_x: bool = True
    jitter_c: bool = True
    jitter_v: bool = True
    jitter_b: bool = True

    # buttons
    click_btn1: str = "LButton"
    click_btn2: str = "LButton"
    click_btn3: str = "LButton"

    # general
    is_auto_start: bool = False
    is_cursor_lock: bool = False
    is_global_hotkeys: bool = False


class ConfigStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.ini_path = self.base_dir / f"{APP_NAME}Settings.ini"

    def load(self, settings: Settings) -> Settings:
        if not self.ini_path.exists():
            return settings
        cp = configparser.ConfigParser()
        cp.read(self.ini_path, encoding="utf-8")
        s = settings
        get = cp.get
        getint = cp.getint
        getbool = cp.getboolean
        if cp.has_section("Delays"):
            s.click1_hold_ms = getint("Delays", "Click1_HoldMs", fallback=s.click1_hold_ms)
            s.click1_gap_ms = getint("Delays", "Click1_GapMs", fallback=s.click1_gap_ms)
            s.click2_hold_ms = getint("Delays", "Click2_HoldMs", fallback=s.click2_hold_ms)
            s.click2_gap_ms = getint("Delays", "Click2_GapMs", fallback=s.click2_gap_ms)
            s.click3_hold_ms = getint("Delays", "Click3_HoldMs", fallback=s.click3_hold_ms)
            s.click3_gap_ms = getint("Delays", "Click3_GapMs", fallback=s.click3_gap_ms)
            s.key_spam_delay_ms = getint("Delays", "KeySpamDelayMs", fallback=s.key_spam_delay_ms)
        if cp.has_section("Keys"):
            s.key_spam_d = get("Keys", "DSpam", fallback=s.key_spam_d)
            s.key_spam_s = get("Keys", "SSpam", fallback=s.key_spam_s)
            s.key_spam_a = get("Keys", "ASpam", fallback=s.key_spam_a)
            s.key_click1 = get("Keys", "ClickSeq1", fallback=s.key_click1)
            s.key_click2 = get("Keys", "ClickSeq2", fallback=s.key_click2)
            s.key_click3 = get("Keys", "ClickSeq3", fallback=s.key_click3)
            s.key_jitter = get("Keys", "Jitter", fallback=get("Keys", "Panic", fallback=s.key_jitter))
        if cp.has_section("Enable"):
            s.is_spam_d_enabled = getbool("Enable", "DSpam", fallback=s.is_spam_d_enabled)
            s.is_spam_s_enabled = getbool("Enable", "SSpam", fallback=s.is_spam_s_enabled)
            s.is_spam_a_enabled = getbool("Enable", "ASpam", fallback=s.is_spam_a_enabled)
            s.is_click1_enabled = getbool("Enable", "ClickSeq1", fallback=s.is_click1_enabled)
            s.is_click2_enabled = getbool("Enable", "ClickSeq2", fallback=s.is_click2_enabled)
            s.is_click3_enabled = getbool("Enable", "ClickSeq3", fallback=s.is_click3_enabled)
            s.is_jitter_enabled = getbool("Enable", "Jitter", fallback=getbool("Enable", "Panic", fallback=s.is_jitter_enabled))
        if cp.has_section("Jitter"):
            s.jitter_z = getbool("Jitter", "Z", fallback=s.jitter_z)
            s.jitter_x = getbool("Jitter", "X", fallback=s.jitter_x)
            s.jitter_c = getbool("Jitter", "C", fallback=s.jitter_c)
            s.jitter_v = getbool("Jitter", "V", fallback=s.jitter_v)
            s.jitter_b = getbool("Jitter", "B", fallback=s.jitter_b)
        if cp.has_section("Buttons"):
            s.click_btn1 = get("Buttons", "ClickSeq1_Button", fallback=s.click_btn1)
            s.click_btn2 = get("Buttons", "ClickSeq2_Button", fallback=s.click_btn2)
            s.click_btn3 = get("Buttons", "ClickSeq3_Button", fallback=s.click_btn3)
        if cp.has_section("General"):
            s.is_auto_start = getbool("General", "AutoStart", fallback=s.is_auto_start)
            s.is_cursor_lock = getbool("General", "CursorLock", fallback=s.is_cursor_lock)
            s.is_global_hotkeys = getbool("General", "GlobalHotkeys", fallback=s.is_global_hotkeys)
        return s

    def save(self, s: Settings) -> None:
        cp = configparser.ConfigParser()
        cp["Delays"] = {
            "Click1_HoldMs": str(s.click1_hold_ms),
            "Click1_GapMs": str(s.click1_gap_ms),
            "Click2_HoldMs": str(s.click2_hold_ms),
            "Click2_GapMs": str(s.click2_gap_ms),
            "Click3_HoldMs": str(s.click3_hold_ms),
            "Click3_GapMs": str(s.click3_gap_ms),
            "KeySpamDelayMs": str(s.key_spam_delay_ms),
        }
        cp["Keys"] = {
            "DSpam": s.key_spam_d,
            "SSpam": s.key_spam_s,
            "ASpam": s.key_spam_a,
            "ClickSeq1": s.key_click1,
            "ClickSeq2": s.key_click2,
            "ClickSeq3": s.key_click3,
            "Jitter": s.key_jitter,
        }
        cp["Enable"] = {
            "DSpam": str(int(s.is_spam_d_enabled)),
            "SSpam": str(int(s.is_spam_s_enabled)),
            "ASpam": str(int(s.is_spam_a_enabled)),
            "ClickSeq1": str(int(s.is_click1_enabled)),
            "ClickSeq2": str(int(s.is_click2_enabled)),
            "ClickSeq3": str(int(s.is_click3_enabled)),
            "Jitter": str(int(s.is_jitter_enabled)),
        }
        cp["Jitter"] = {
            "Z": str(int(s.jitter_z)),
            "X": str(int(s.jitter_x)),
            "C": str(int(s.jitter_c)),
            "V": str(int(s.jitter_v)),
            "B": str(int(s.jitter_b)),
        }
        cp["Buttons"] = {
            "ClickSeq1_Button": s.click_btn1,
            "ClickSeq2_Button": s.click_btn2,
            "ClickSeq3_Button": s.click_btn3,
        }
        cp["General"] = {
            "AutoStart": str(int(s.is_auto_start)),
            "CursorLock": str(int(s.is_cursor_lock)),
            "GlobalHotkeys": str(int(s.is_global_hotkeys)),
        }
        with self.ini_path.open("w", encoding="utf-8") as f:
            cp.write(f)
