"""Sound banks: switch between preset configurations (radio, streaming, etc.)."""

import json
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class SoundBank:
    name: str
    keys: dict
    volume: float = 0.8
    channels: int = 1
    device: str = ""


class BankManager:
    """Manages multiple sound banks stored in banks/ directory.

    Each bank is a JSON file:
    {
        "name": "ham_radio",
        "device": "USB Sound Card",
        "channels": 1,
        "volume": 0.7,
        "keys": {"1": "cQ.wav", "2": "73.wav", ...}
    }
    """

    def __init__(self, banks_dir: str = "banks/"):
        self.banks_dir = Path(banks_dir)
        self.banks_dir.mkdir(exist_ok=True)
        self._banks: dict[str, SoundBank] = {}
        self._current: str | None = None
        self._load_all()

    def _load_all(self) -> None:
        for f in sorted(self.banks_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                bank = SoundBank(
                    name=data["name"],
                    keys=data.get("keys", {}),
                    volume=data.get("volume", 0.8),
                    channels=data.get("channels", 1),
                    device=data.get("device", ""),
                )
                self._banks[bank.name] = bank
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[bank] Skip {f.name}: {e}")

    def list_banks(self) -> list[str]:
        return sorted(self._banks.keys())

    def get(self, name: str) -> SoundBank | None:
        return self._banks.get(name)

    def save(self, bank: SoundBank) -> None:
        path = self.banks_dir / f"{bank.name}.json"
        data = {
            "name": bank.name,
            "device": bank.device,
            "channels": bank.channels,
            "volume": bank.volume,
            "keys": bank.keys,
        }
        path.write_text(json.dumps(data, indent=2))
        self._banks[bank.name] = bank
        print(f"[bank] Saved: {path}")

    def load(self, name: str) -> SoundBank | None:
        if name not in self._banks:
            # Try reloading from disk
            self._load_all()
        bank = self._banks.get(name)
        if bank:
            self._current = name
            print(f"[bank] Loaded bank: {name} ({len(bank.keys)} keys)")
        return bank

    @property
    def current(self) -> SoundBank | None:
        return self._banks.get(self._current) if self._current else None
