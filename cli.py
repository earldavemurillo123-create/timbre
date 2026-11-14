"""Timbre command-line interface.

Examples:
  python cli.py serve                                 # start the web studio
  python cli.py serve --engine demo                   # try the UI without a model
  python cli.py voices add "Narrator" clip.wav --consent
  python cli.py voices list
  python cli.py speak narrator-1a2b3c "Hello there." -o hello.wav
  python cli.py batch narrator-1a2b3c script.txt
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from timbre.config import settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="timbre", description="Local voice cloning studio.")
    parser.add_argument("--engine", default=None, help="xtts (default) or demo")
    parser.add_argument("--device", default=None, help="auto, cpu or cuda")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Start the web studio")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=7860)

    voices = sub.add_parser("voices", help="Manage saved voices")
    vsub = voices.add_subparsers(dest="action", required=True)
    vsub.add_parser("list", help="List saved voices")
    add = vsub.add_parser("add", help="Save a reference clip as a voice")
    add.add_argument("name")
    add.add_argument("clip", type=Path)
    add.add_argument("--consent", action="store_true", help="Confirm you have permission to use this voice")
    rm = vsub.add_parser("delete", help="Delete a saved voice")
    rm.add_argument("voice_id")

    for name, help_text in (("speak", "Generate speech from text"), ("batch", "Generate one clip per script line")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("voice_id")
        p.add_argument("text" if name == "speak" else "script", help="Text to say" if name == "speak" else "Path to a .txt script")
        p.add_argument("-l", "--language", default="en")
        p.add_argument("-s", "--speed", type=float, default=1.0)
        p.add_argument("-o", "--out", type=Path, help="Copy the result to this path")

    args = parser.parse_args(argv)
    if args.engine:
        settings.engine = args.engine
    if args.device:
        settings.device = args.device

    if args.command == "serve":
        import uvicorn

        from timbre.server import create_app

        print(f"Timbre studio: http://{args.host}:{args.port}")
        uvicorn.run(create_app(settings), host=args.host, port=args.port)
        return 0

    from timbre.audio import AudioError
    from timbre.studio import Studio

    needs_engine = args.command in ("speak", "batch")
    studio = Studio(settings) if needs_engine else None
    library = studio.voices if studio else _library()

    try:
        if args.command == "voices":
            if args.action == "list":
                voices = library.list()
                if not voices:
                    print("No saved voices yet. Add one with: python cli.py voices add NAME CLIP --consent")
                for v in voices:
                    print(f"{v.id:<32} {v.name:<24} {v.duration:>5.1f}s")
            elif args.action == "add":
                voice = library.add(args.name, args.clip, consent=args.consent)
                print(f"Saved voice '{voice.name}' as {voice.id} ({voice.duration:.1f}s of speech)")
            elif args.action == "delete":
                library.delete(args.voice_id)
                print(f"Deleted {args.voice_id}")
            return 0

        print(f"Loading {studio.engine.label} on {studio.engine.device}...", file=sys.stderr)
        studio.load()
        if args.command == "speak":
            take = studio.speak(args.voice_id, args.text, args.language, args.speed)
        else:
            script = Path(args.script).read_text("utf-8")
            take = studio.batch(args.voice_id, script, args.language, args.speed)

        folder = settings.takes_dir / take.id
        print(f"Take {take.number}: {take.duration:.1f}s, saved to {folder / 'take.wav'}")
        if args.out:
            shutil.copy(folder / "take.wav", args.out)
            print(f"Copied to {args.out}")
        return 0
    except PermissionError as exc:
        print(f"{exc} Add --consent to confirm.", file=sys.stderr)
    except (AudioError, ValueError, KeyError, RuntimeError, FileNotFoundError) as exc:
        print(f"Error: {exc.args[0] if exc.args else exc}", file=sys.stderr)
    return 1


def _library():
    from timbre.voices import VoiceLibrary

    settings.ensure_dirs()
    return VoiceLibrary(settings)


if __name__ == "__main__":
    raise SystemExit(main())
