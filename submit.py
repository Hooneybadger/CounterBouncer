#!/usr/bin/env python3
"""Build and email the IDBLAB algorithm submission."""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent
SOURCE_DIR = ROOT / "src"
ARCHIVE_PATH = ROOT / "dist" / "src.zip"
RECIPIENT = "submission@optichallenge.com"
SUBJECT = "Team IDBLAB Algorithm Submission"
BODY = "Please find the attached algorithm submission file."
MAX_ARCHIVE_SIZE = 15_000_000
EXCLUDED_PARTS = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache"}
# 평가 서버가 자기 utils.py로 덮어쓰므로 제출 zip에 넣지 않는다(대회 규칙). 우리 src/utils.py
# 는 대회 원본과 바이트 동일이라 import 대상(Bay·check_feasibility·_poly_from_verts 등)은
# 서버 utils.py가 그대로 제공한다.
EXCLUDED_NAMES = {"utils.py",
                  # ★네이티브 엔진은 base64 텍스트(scan_engine_ext.b64=import용 abi3 확장,
                  #   scan_engine.b64=ctypes/memfd 폴백 평문 .so)로만 동봉한다 — 런타임에 .so로 디코딩해
                  #   import/load. 직접 .so/.bin은 (a)Gmail이 .so-in-zip을 확장자로 차단 (b)서버 도달해도
                  #   ctypes 일탈로 미로드라 *절대* 제출에 안 넣는다. 런타임 디코딩 산물(*.abi3.so,
                  #   lib_scan_engine.so)이 src에 남아도 아래 `.so` 확장자 배제로 zip서 빠진다.
                  "scan_engine.bin", "scan_engine"}
# 제출에 반드시 들어가야 하는 모듈(myalgorithm이 import하는 우리 코드). 검증용.
REQUIRED_NAMES = {"myalgorithm.py", "constructor.py", "alns.py",
                  "raster_engine.py", "baseline_greedy.py", "relax_repair.py",
                  # ★네이티브 엔진 동봉본(없으면 cengine 영영 폴백) — import용 abi3 확장 + ctypes 폴백 평문
                  "scan_engine_ext.b64", "scan_engine.b64"}


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Load simple KEY=VALUE entries without overriding shell variables."""
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def source_files() -> list[Path]:
    if not SOURCE_DIR.is_dir():
        raise SystemExit(f"Source directory does not exist: {SOURCE_DIR}")

    files = [
        path
        for path in SOURCE_DIR.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and not any(part in EXCLUDED_PARTS for part in path.relative_to(SOURCE_DIR).parts)
        and path.name not in EXCLUDED_NAMES
        # ★.so는 무엇이든 동봉 금지 — Gmail이 .so-in-zip을 차단하고, 런타임 디코딩 산물(*.abi3.so,
        #   lib_scan_engine.so)이 src에 남아도 zip엔 안 들어가게 한다. 엔진은 .b64로만 간다.
        and not path.name.endswith((".pyc", ".pyo", ".so"))
    ]
    if SOURCE_DIR / "myalgorithm.py" not in files:
        raise SystemExit("src/myalgorithm.py is required.")
    return sorted(files)


def build_archive(output: Path) -> Path:
    files = source_files()
    output.parent.mkdir(parents=True, exist_ok=True)

    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, path.relative_to(SOURCE_DIR))

    with ZipFile(output) as archive:
        names = archive.namelist()
        if "myalgorithm.py" not in names:
            raise SystemExit("Archive validation failed: myalgorithm.py is not at ZIP root.")
        if any(name.startswith("src/") for name in names):
            raise SystemExit("Archive validation failed: src directory was included in ZIP.")
        if "utils.py" in names:
            raise SystemExit("Archive validation failed: utils.py must be excluded (server provides it).")
        missing = REQUIRED_NAMES - set(names)
        if missing:
            raise SystemExit(f"Archive validation failed: missing required modules {sorted(missing)}.")
        # ★.so 직접 동봉 금지(Gmail 차단·서버 미로드) — 엔진은 .b64로만. 런타임 디코딩 산물이 새어들면 차단.
        so_in_zip = [n for n in names if n.endswith(".so")]
        if so_in_zip:
            raise SystemExit(f"Archive validation failed: .so must NOT be shipped (Gmail blocks): {so_in_zip}.")
        if archive.testzip() is not None:
            raise SystemExit("Archive validation failed: corrupt ZIP member detected.")

    size = output.stat().st_size
    if size > MAX_ARCHIVE_SIZE:
        output.unlink(missing_ok=True)
        raise SystemExit(f"Archive exceeds 15 MB: {size / 1024 / 1024:.2f} MB")

    return output


def send_archive(archive: Path) -> None:
    from_email = os.environ.get("TEAM_EMAIL")
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_user = os.environ.get("SMTP_USER") or from_email
    smtp_password = os.environ.get("SMTP_PASSWORD")

    if not from_email:
        raise SystemExit("Set TEAM_EMAIL in .env.")
    if not smtp_host:
        raise SystemExit("Set SMTP_HOST in .env.")
    if not smtp_password:
        raise SystemExit("Set SMTP_PASSWORD in .env.")

    message = EmailMessage()
    message["From"] = from_email
    message["To"] = RECIPIENT
    message["Subject"] = SUBJECT
    message.set_content(BODY)
    message.add_attachment(
        archive.read_bytes(),
        maintype="application",
        subtype="zip",
        filename=archive.name,
    )

    attachments = list(message.iter_attachments())
    if len(attachments) != 1:
        raise SystemExit("Email validation failed: exactly one attachment is required.")

    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, 587) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)


def main() -> None:
    load_dotenv()
    archive = build_archive(ARCHIVE_PATH)
    print(f"Built: {archive} ({archive.stat().st_size:,} bytes)")
    send_archive(archive)
    print(f"Sent: {os.environ['TEAM_EMAIL']} -> {RECIPIENT}")


if __name__ == "__main__":
    main()
