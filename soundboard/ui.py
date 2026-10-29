"""Curses-based TUI for NutTx."""

import curses
from .engine import Engine
from .safety import Safety


class TUI:
    """Terminal UI: shows sound list, key bindings, and playback status.

    All key handling happens in the main curses loop -- there is no
    separate stdin reader, so hotkeys and UI keys can't race.
    """

    def __init__(self, engine: Engine, keys: dict, cfg: dict,
                 playlog=None, safety: Safety | None = None):
        self.engine = engine
        self.keys = keys
        self.cfg = cfg
        self.playlog = playlog
        self.safety = safety or Safety(engine, cfg)
        self._running = False

    def run(self) -> None:
        setup_colors()
        self.safety.start_watchdog()
        self._running = True
        curses.wrapper(self._main_loop)
        self.engine.stop_all()

    def _main_loop(self, stdscr) -> None:
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.keypad(True)

        while self._running:
            self._draw(stdscr)
            ch = stdscr.getch()
            if ch == -1:
                continue  # nothing typed
            c = chr(ch) if 32 <= ch < 127 else ""
            if c == "q":
                self._running = False
            elif c == "l":
                self.engine._load_all()
            elif c == "m":
                # Mute toggle: flip global volume
                if self.safety.is_muted():
                    self.safety.unmute()
                else:
                    self.engine.global_volume = 0.0
                    self.safety.touch()
            elif c == "d":
                self.safety.duck()
            elif c == "u":
                self.safety.unduck()
            elif c in self.keys:
                sound_name = self.keys[c]
                ok = self.engine.play(sound_name)
                self.safety.touch()
                if self.playlog:
                    self.playlog.record(c, sound_name, "keyboard", ok)

    def _draw(self, stdscr) -> None:
        stdscr.erase()
        h, w = stdscr.getmaxyx()

        # Title bar
        title = " N u t T x "
        device_name = "default"
        if self.engine.device is not None:
            try:
                device_name = __import__("sounddevice").query_devices(self.engine.device)["name"]
            except Exception:
                pass
        header = f"{title}  |  {self.engine.sample_rate} Hz  |  {device_name}"
        stdscr.addstr(0, 0, header[:w - 1], curses.A_BOLD | curses.color_pair(1) if curses.has_colors() else curses.A_BOLD)

        # Volume bar
        vol = self.engine.global_volume
        vol_bar = "#" * int(vol * 20) + "." * (20 - int(vol * 20))
        vol_label = f" VOL [{vol_bar}] {vol:.0%}"
        stdscr.addstr(1, 0, vol_label[:w - 1])

        # Sound table
        y = 3
        stdscr.addstr(y, 0, " KEY  SOUND NAME                    STATUS", curses.A_UNDERLINE)
        y += 1

        # Sort keys for display
        sorted_keys = sorted(self.keys.items(), key=lambda x: x[0])
        for key, sound_name in sorted_keys:
            if y >= h - 3:
                break
            status = "  >> PLAYING" if self.engine.is_playing(sound_name) else ""
            line = f"  {key}    {sound_name:<30s} {status}"
            attr = curses.A_BOLD if self.engine.is_playing(sound_name) else curses.A_NORMAL
            try:
                stdscr.addstr(y, 0, line[:w - 1], attr)
            except curses.error:
                pass
            y += 1

        # Footer / help
        footer = " [1-0] play  [m] mute  [d] duck  [u] unduck  [l] reload  [q] quit"
        try:
            stdscr.addstr(h - 1, 0, footer[:w - 1], curses.A_DIM)
        except curses.error:
            pass

        stdscr.refresh()


def setup_colors() -> None:
    if not curses.has_colors():
        return
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_YELLOW, -1)
    curses.init_pair(2, curses.COLOR_GREEN, -1)
