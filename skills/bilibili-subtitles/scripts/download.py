#!/usr/bin/env python3
"""Download public Bilibili subtitle tracks as SRT files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import http.cookiejar
import json
import os
import re
import shutil
import ssl
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


API_BASE = "https://api.bilibili.com"
LOGIN_BASE = "https://passport.bilibili.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)
MIXIN_KEY_ENC_TAB = (
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
)


def ssl_context() -> ssl.SSLContext:
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


SSL_CONTEXT = ssl_context()


class BilibiliError(RuntimeError):
    """Raised when Bilibili returns an application or transport error."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Bilibili subtitle tracks as SRT files.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--mid", help="Bilibili creator MID.")
    source.add_argument("--space-url", help="Bilibili creator space URL.")
    source.add_argument(
        "--bvid",
        nargs="+",
        help="One or more Bilibili BV identifiers.",
    )
    source.add_argument(
        "--video-list",
        type=Path,
        help="JSON list containing BVID strings or {bvid,title} objects.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Project output directory. Defaults to PPT Master projects.",
    )
    parser.add_argument(
        "--ppt-master-root",
        type=Path,
        help="PPT Master repository root used for the default output.",
    )
    parser.add_argument(
        "--cookie-file",
        type=Path,
        help="Optional Netscape-format cookie file. Otherwise use QR login.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="Concurrent video workers (default: 8).",
    )
    parser.add_argument(
        "--login-timeout",
        type=int,
        default=180,
        help="QR login timeout in seconds (default: 180).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Refresh and overwrite existing SRT files.",
    )
    parser.add_argument(
        "--zip",
        action="store_true",
        help="Create a ZIP archive containing the subtitles directory.",
    )
    return parser.parse_args()


def request_json(
    url: str,
    cookie_header: str = "",
    referer: str = "https://www.bilibili.com/",
    retries: int = 4,
) -> dict[str, Any]:
    last_error: Exception | None = None
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": referer,
        "User-Agent": USER_AGENT,
    }
    if cookie_header:
        headers["Cookie"] = cookie_header

    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(
                request,
                timeout=30,
                context=SSL_CONTEXT,
            ) as response:
                payload = json.load(response)
            if isinstance(payload.get("code"), int) and payload["code"] != 0:
                raise BilibiliError(
                    f"Bilibili {payload['code']}: "
                    f"{payload.get('message') or 'unknown error'}"
                )
            return payload
        except Exception as error:  # noqa: BLE001 - retry network/API failures
            last_error = error
            if attempt + 1 < retries:
                time.sleep(0.25 * (2**attempt))
    raise BilibiliError(str(last_error))


def cookie_header_from_file(cookie_file: Path) -> str:
    cookies: list[str] = []
    for raw_line in cookie_file.read_text(encoding="utf-8").splitlines():
        line = raw_line
        if line.startswith("#HttpOnly_"):
            line = line.removeprefix("#HttpOnly_")
        elif not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) >= 7:
            cookies.append(f"{fields[5]}={fields[6]}")
    if not cookies:
        raise BilibiliError(f"No cookies found in {cookie_file}")
    return "; ".join(cookies)


def qr_login(timeout_seconds: int) -> str:
    try:
        import qrcode
    except ImportError as error:
        raise BilibiliError(
            "QR login requires qrcode. Install resources/requirements.txt."
        ) from error

    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=SSL_CONTEXT),
        urllib.request.HTTPCookieProcessor(cookie_jar),
    )
    opener.addheaders = [("User-Agent", USER_AGENT)]

    generate_url = f"{LOGIN_BASE}/x/passport-login/web/qrcode/generate"
    with opener.open(generate_url, timeout=30) as response:
        payload = json.load(response)
    if payload.get("code") != 0:
        raise BilibiliError(
            f"Unable to create QR login: {payload.get('message')}"
        )

    login_url = payload["data"]["url"]
    qrcode_key = payload["data"]["qrcode_key"]
    with tempfile.TemporaryDirectory(prefix="bilibili-qr-login-") as temp_dir:
        qr_path = Path(temp_dir) / "bilibili-login.png"
        qrcode.make(login_url).save(qr_path)
        print(f"QR_CODE: {qr_path}", flush=True)
        print(
            "Scan the QR code with the Bilibili app and confirm login.",
            flush=True,
        )

        deadline = time.monotonic() + timeout_seconds
        scan_reported = False
        while time.monotonic() < deadline:
            poll_url = (
                f"{LOGIN_BASE}/x/passport-login/web/qrcode/poll?"
                + urllib.parse.urlencode({"qrcode_key": qrcode_key})
            )
            with opener.open(poll_url, timeout=30) as response:
                poll = json.load(response)
            code = poll.get("data", {}).get("code")
            if code == 0:
                cookies = [f"{item.name}={item.value}" for item in cookie_jar]
                if not cookies:
                    raise BilibiliError(
                        "Login succeeded but no session cookie was returned."
                    )
                print("LOGIN: confirmed", flush=True)
                return "; ".join(cookies)
            if code == 86090 and not scan_reported:
                print("LOGIN: scanned, waiting for confirmation", flush=True)
                scan_reported = True
            if code == 86038:
                raise BilibiliError("The QR code expired. Run the command again.")
            time.sleep(2)

    raise BilibiliError("QR login timed out.")


def mid_from_args(args: argparse.Namespace) -> str | None:
    if args.mid:
        if not args.mid.isdigit():
            raise BilibiliError("--mid must contain digits only.")
        return args.mid
    if args.space_url:
        match = re.search(r"space\.bilibili\.com/(\d+)", args.space_url)
        if not match:
            raise BilibiliError("Unable to find a MID in --space-url.")
        return match.group(1)
    return None


def wbi_mixin_key(cookie_header: str) -> str:
    payload = request_json(
        f"{API_BASE}/x/web-interface/nav",
        cookie_header,
    )
    wbi_img = payload.get("data", {}).get("wbi_img", {})
    img_url = str(wbi_img.get("img_url") or "")
    sub_url = str(wbi_img.get("sub_url") or "")
    if not img_url or not sub_url:
        raise BilibiliError("Unable to retrieve WBI signing keys.")

    raw_key = (
        Path(urllib.parse.urlparse(img_url).path).stem
        + Path(urllib.parse.urlparse(sub_url).path).stem
    )
    try:
        return "".join(raw_key[index] for index in MIXIN_KEY_ENC_TAB)[:32]
    except IndexError as error:
        raise BilibiliError("Bilibili returned invalid WBI signing keys.") from error


def signed_wbi_query(params: dict[str, Any], mixin_key: str) -> str:
    signed_params = {
        key: re.sub(r"[!'()*]", "", str(value))
        for key, value in params.items()
    }
    signed_params["wts"] = str(int(time.time()))
    query = urllib.parse.urlencode(sorted(signed_params.items()))
    signature = hashlib.md5(
        f"{query}{mixin_key}".encode("utf-8")
    ).hexdigest()
    return f"{query}&w_rid={signature}"


def creator_archive_videos(
    mid: str,
    cookie_header: str,
) -> list[dict[str, str]]:
    mixin_key = wbi_mixin_key(cookie_header)
    videos: list[dict[str, str]] = []
    seen_bvids: set[str] = set()
    page_number = 1
    total_count: int | None = None

    while total_count is None or len(videos) < total_count:
        params = {
            "mid": mid,
            "order": "pubdate",
            "order_avoided": "true",
            "platform": "web",
            "pn": page_number,
            "ps": 50,
            "web_location": 1550101,
        }
        url = (
            f"{API_BASE}/x/space/wbi/arc/search?"
            + signed_wbi_query(params, mixin_key)
        )
        payload = request_json(
            url,
            cookie_header,
            referer=f"https://space.bilibili.com/{mid}/upload/video",
        )
        data = payload.get("data") or {}
        page = data.get("page") or {}
        if total_count is None:
            total_count = int(page.get("count") or 0)

        page_videos = (data.get("list") or {}).get("vlist") or []
        if not page_videos:
            break
        for item in page_videos:
            bvid = str(item.get("bvid") or "")
            if bvid and bvid not in seen_bvids:
                seen_bvids.add(bvid)
                videos.append(
                    {"bvid": bvid, "title": str(item.get("title") or bvid)}
                )
        page_number += 1
        time.sleep(0.12)

    if total_count and len(videos) < total_count:
        raise BilibiliError(
            f"Creator archive returned {len(videos)} of {total_count} videos."
        )
    return videos


def creator_dynamic_videos(
    mid: str,
    cookie_header: str,
) -> list[dict[str, str]]:
    videos: list[dict[str, str]] = []
    seen_bvids: set[str] = set()
    seen_offsets: set[str] = set()
    offset = ""

    while True:
        query = {"host_mid": mid}
        if offset:
            query["offset"] = offset
        url = (
            f"{API_BASE}/x/polymer/web-dynamic/v1/feed/space?"
            + urllib.parse.urlencode(query)
        )
        payload = request_json(
            url,
            cookie_header,
            referer=f"https://space.bilibili.com/{mid}/dynamic",
        )
        data = payload.get("data") or {}
        for item in data.get("items") or []:
            if item.get("type") != "DYNAMIC_TYPE_AV":
                continue
            archive = (
                item.get("modules", {})
                .get("module_dynamic", {})
                .get("major", {})
                .get("archive", {})
            )
            bvid = archive.get("bvid")
            if bvid and bvid not in seen_bvids:
                seen_bvids.add(bvid)
                videos.append(
                    {"bvid": bvid, "title": archive.get("title") or bvid}
                )

        if not data.get("has_more"):
            break
        next_offset = str(data.get("offset") or "")
        if not next_offset or next_offset in seen_offsets:
            raise BilibiliError("Dynamic pagination returned a repeated offset.")
        seen_offsets.add(next_offset)
        offset = next_offset
        time.sleep(0.12)

    return videos


def creator_videos(mid: str, cookie_header: str) -> list[dict[str, str]]:
    try:
        return creator_archive_videos(mid, cookie_header)
    except BilibiliError as archive_error:
        print(
            "WARN: creator archive search failed; "
            "falling back to the dynamic feed, which may omit old videos: "
            f"{archive_error}",
            file=sys.stderr,
            flush=True,
        )
        return creator_dynamic_videos(mid, cookie_header)


def videos_from_json(video_list: Path) -> list[dict[str, str]]:
    payload = json.loads(video_list.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("videos")
    if not isinstance(payload, list):
        raise BilibiliError("Video list JSON must be an array.")

    videos: list[dict[str, str]] = []
    for item in payload:
        if isinstance(item, str):
            videos.append({"bvid": item, "title": item})
        elif isinstance(item, dict) and item.get("bvid"):
            videos.append(
                {
                    "bvid": str(item["bvid"]),
                    "title": str(item.get("title") or item["bvid"]),
                }
            )
        else:
            raise BilibiliError("Each video-list item must contain a BVID.")
    return videos


def safe_file_component(value: str, max_bytes: int = 150) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip() or "untitled"
    encoded = cleaned.encode("utf-8")
    while len(encoded) > max_bytes:
        cleaned = cleaned[:-1]
        encoded = cleaned.encode("utf-8")
    return cleaned


def srt_time(value: float) -> str:
    if not value:
        return "00:00:00,000"
    hours = int(value // 3600)
    minutes = int((value // 60) % 60)
    seconds = int(value % 60)
    milliseconds = int((value % 1) * 1000)
    return (
        f"{hours:02d}:{minutes:02d}:{seconds:02d},"
        f"{milliseconds:03d}"
    )


def to_srt(body: list[dict[str, Any]]) -> str:
    cues = []
    for index, item in enumerate(body, start=1):
        content = str(item.get("content") or "").strip()
        cues.append(
            f"{index}\n"
            f"{srt_time(float(item.get('from') or 0))} --> "
            f"{srt_time(float(item.get('to') or 0))}\n"
            f"{content}"
        )
    return "\n\n".join(cues) + "\n"


def select_track(tracks: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in tracks:
        if item.get("lan") == "ai-zh" and item.get("subtitle_url"):
            return item
    for item in tracks:
        language = str(item.get("lan") or "").lower()
        if language.startswith("zh") and item.get("subtitle_url"):
            return item
    return next((item for item in tracks if item.get("subtitle_url")), None)


def valid_existing_srt(file_path: Path) -> bool:
    if not file_path.is_file():
        return False
    try:
        prefix = file_path.read_text(encoding="utf-8")[:80]
    except (OSError, UnicodeError):
        return False
    return bool(
        re.match(
            r"1\n\d{2}:\d{2}:\d{2},\d{3} --> "
            r"\d{2}:\d{2}:\d{2},\d{3}",
            prefix,
        )
    )


def download_video(
    video: dict[str, str],
    index: int,
    subtitles_dir: Path,
    cookie_header: str,
    overwrite: bool,
) -> dict[str, Any]:
    bvid = video["bvid"]
    referer = f"https://www.bilibili.com/video/{bvid}"
    try:
        view = request_json(
            f"{API_BASE}/x/web-interface/view?"
            + urllib.parse.urlencode({"bvid": bvid}),
            cookie_header,
            referer,
        )
        aid = view["data"]["aid"]
        title = view["data"].get("title") or video["title"]
        pages = view["data"].get("pages") or [
            {"page": 1, "cid": view["data"]["cid"], "part": title}
        ]
        output_files: list[str] = []

        for page_info in pages:
            player = request_json(
                f"{API_BASE}/x/player/wbi/v2?"
                + urllib.parse.urlencode(
                    {"aid": aid, "cid": page_info["cid"]}
                ),
                cookie_header,
                referer,
            )
            tracks = (
                player.get("data", {})
                .get("subtitle", {})
                .get("subtitles", [])
            )
            track = select_track(tracks)
            if not track:
                continue

            part_suffix = (
                f"_P{int(page_info.get('page') or 1):02d}"
                if len(pages) > 1
                else ""
            )
            part_title = title
            if len(pages) > 1 and page_info.get("part"):
                part_title = f"{title}_{page_info['part']}"
            file_name = (
                f"{index + 1:04d}_{bvid}{part_suffix}_"
                f"{safe_file_component(part_title)}.srt"
            )
            output_path = subtitles_dir / file_name
            if not overwrite and valid_existing_srt(output_path):
                output_files.append(str(output_path))
                continue

            subtitle_url = str(track["subtitle_url"])
            if subtitle_url.startswith("//"):
                subtitle_url = f"https:{subtitle_url}"
            subtitle = request_json(
                subtitle_url,
                cookie_header,
                referer,
            )
            body = subtitle.get("body")
            if not isinstance(body, list) or not body:
                continue
            output_path.write_text(to_srt(body), encoding="utf-8")
            output_files.append(str(output_path))

        return {
            "sequence": index + 1,
            "bvid": bvid,
            "title": title,
            "status": "saved" if output_files else "no_subtitle",
            "files": output_files,
        }
    except Exception as error:  # noqa: BLE001 - report each failed video
        return {
            "sequence": index + 1,
            "bvid": bvid,
            "title": video["title"],
            "status": "failed",
            "error": str(error),
            "files": [],
        }


def write_csv(path: Path, rows: list[dict[str, Any]], failed: bool) -> None:
    headers = ["sequence", "bvid", "title"]
    if failed:
        headers.append("error")
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in headers})


def find_ppt_master_root(args: argparse.Namespace) -> Path:
    candidates: list[Path] = []
    if args.ppt_master_root:
        candidates.append(args.ppt_master_root)

    if os.environ.get("PPT_MASTER_ROOT"):
        candidates.append(Path(os.environ["PPT_MASTER_ROOT"]))

    current = Path.cwd()
    candidates.extend(
        [
            current,
            current.parent / "ppt-master",
            Path(__file__).resolve().parents[3].parent / "ppt-master",
        ]
    )
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if (resolved / "skills" / "ppt-master" / "SKILL.md").is_file():
            return resolved
    raise BilibiliError(
        "Unable to locate PPT Master. Use --ppt-master-root, "
        "PPT_MASTER_ROOT, or --output."
    )


def default_output(args: argparse.Namespace, mid: str | None) -> Path:
    repository_root = find_ppt_master_root(args)
    if mid:
        project_name = f"bilibili-subtitles-{mid}"
    elif args.bvid and len(args.bvid) == 1:
        project_name = f"bilibili-subtitles-{args.bvid[0]}"
    else:
        project_name = "bilibili-subtitles-batch"
    return repository_root / "projects" / project_name


def main() -> int:
    args = parse_args()
    if not 1 <= args.concurrency <= 32:
        raise BilibiliError("--concurrency must be between 1 and 32.")

    mid = mid_from_args(args)
    cookie_header = (
        cookie_header_from_file(args.cookie_file)
        if args.cookie_file
        else qr_login(args.login_timeout)
    )

    if mid:
        videos = creator_videos(mid, cookie_header)
    elif args.bvid:
        videos = [{"bvid": item, "title": item} for item in args.bvid]
    else:
        videos = videos_from_json(args.video_list)
    if not videos:
        raise BilibiliError("No videos were found.")

    output_dir = (args.output or default_output(args, mid)).resolve()
    subtitles_dir = output_dir / "subtitles"
    subtitles_dir.mkdir(parents=True, exist_ok=True)
    print(f"VIDEOS: {len(videos)}", flush=True)
    print(f"OUTPUT: {output_dir}", flush=True)

    results: list[dict[str, Any] | None] = [None] * len(videos)
    progress_lock = threading.Lock()
    completed = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        future_map = {
            executor.submit(
                download_video,
                video,
                index,
                subtitles_dir,
                cookie_header,
                args.overwrite,
            ): index
            for index, video in enumerate(videos)
        }
        for future in as_completed(future_map):
            index = future_map[future]
            results[index] = future.result()
            with progress_lock:
                completed += 1
                if completed % 20 == 0 or completed == len(videos):
                    print(
                        f"PROGRESS: {completed}/{len(videos)}",
                        flush=True,
                    )

    finalized = [item for item in results if item is not None]
    no_subtitle = [
        item for item in finalized if item["status"] == "no_subtitle"
    ]
    failed = [item for item in finalized if item["status"] == "failed"]
    if no_subtitle:
        write_csv(
            output_dir / "no-subtitle-videos.csv",
            no_subtitle,
            failed=False,
        )
    if failed:
        write_csv(output_dir / "failed-videos.csv", failed, failed=True)

    if args.zip:
        archive_base = output_dir / output_dir.name
        archive_path = shutil.make_archive(
            str(archive_base),
            "zip",
            root_dir=output_dir,
            base_dir="subtitles",
        )
        print(f"ARCHIVE: {archive_path}", flush=True)

    saved = sum(item["status"] == "saved" for item in finalized)
    files = sum(len(item["files"]) for item in finalized)
    print(
        f"DONE: saved={saved} no_subtitle={len(no_subtitle)} "
        f"failed={len(failed)} files={files}",
        flush=True,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BilibiliError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2) from error
