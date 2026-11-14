import os, json, re, time, requests, uuid, base64, subprocess, threading, sqlite3, math, wave, struct
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).parent
OUT_DIR = Path(os.getenv("OUTPUT_DIR", "/data/insta-reels"))
OUT_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DIR = OUT_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="Kids Wild Animal Stories + Flow Controller", version="0.3.0")
run_auth = HTTPBearer(auto_error=False)

def env(name, default=""):
    return os.getenv(name, default).strip()

def gemini_story():
    key = env("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY missing in Railway Variables.")
    model = env("GEMINI_MODEL", "gemini-2.5-flash")
    prompt = r"""
Create ONE original, child-friendly Hindi animated story for Instagram Reels.
Audience: children. Theme: poor-vs-rich wild animal stories, friendship, kindness,
courage, cleverness, helping others, fair outcomes. No graphic violence, cruelty,
humiliation, frightening scenes, or dangerous imitation.
Choose different wild animal leads across stories (tiger, rabbit, lion, elephant,
fox, panda, deer, monkey, bear, etc.). Avoid repeating the lead animal used in
recent_stories below when possible.
Recent story titles:
""" + json.dumps(load_recent_titles(), ensure_ascii=False) + r"""

Choose either:
- "short": one complete story, 4-5 clips, total 40-50 seconds; OR
- "series": a longer story intended for 2-4 Instagram parts. Each uploaded part
  itself has 4-5 clips of about 10 seconds (40-50 seconds). Part 1 must end on
  a clear, child-safe cliffhanger. Include a coherent plan for later parts.
Use poor/rich contrast only as a story setup, not as a message that wealth makes
someone better. Resolve with kindness, effort, fairness, or friendship.
Keep character appearances consistent within the entire story/series. New stories
can have completely different characters.
Return ONLY valid JSON with this exact structure:
{
 "format":"short or series",
 "series_title":"short Hindi title",
 "lead_animal":"animal",
 "part_number":1,
 "total_parts":1,
 "part_title":"Hindi title for this upload",
 "characters":[{"name":"...","animal":"...","look":"specific visual appearance and clothes"}],
 "clips":[
   {"clip_number":1,"duration_seconds":10,
    "visual_prompt":"Detailed cinematic 3D animation prompt for this exact scene. Repeat the relevant character appearance for continuity.",
    "action":"What happens",
    "voiceover_hi":"Short natural Hindi narration for about 8-10 seconds",
    "overlay_text":"Short readable Hindi text"},
   {"clip_number":2,"duration_seconds":10,"visual_prompt":"...","action":"...","voiceover_hi":"...","overlay_text":"..."}
 ],
 "ending_type":"cliffhanger or complete",
 "end_card_text":"Hindi follow/next-part CTA appropriate to ending",
 "full_voiceover_hi":"All clip narration combined in order",
 "caption":"Hindi Instagram caption mentioning part number if series",
 "hashtags":["#..."]
}
Requirements:
- exactly 4 or 5 clips, each 10 seconds.
- each clip prompt must be usable independently in a text-to-video generator.
- repeat character details in every relevant visual_prompt; same outfit/colors/face.
- 9:16 vertical, colorful high-quality cinematic 3D cartoon animation, smooth movement,
  expressive faces, clear composition, no logos/watermarks.
- Short story: total_parts=1 and ending_type=complete.
- Series: total_parts between 2 and 4; part 1 has cliffhanger; later parts continue same story.
- Include CTA in end_card_text: for non-final series part say
  "Part 2 देखने के लिए Follow करो ❤️" (adjust next part number);
  final part/short story say "ऐसी और कहानियों के लिए Follow करो ❤️".
- Do not use real people, copyrighted characters, or copied story plots.
"""
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    # Send the API key in a header, not the URL, so it is less likely to appear
    # in request logs, browser screenshots, or copied URLs.
    try:
        r=requests.post(url, headers={"x-goog-api-key": key},
            json={"contents":[{"parts":[{"text":prompt}]}],
                  "generationConfig":{"temperature":0.9,"responseMimeType":"application/json"}},
            timeout=90)
    except requests.RequestException as e:
        raise RuntimeError(f"Could not reach Gemini API: {type(e).__name__}: {e}") from e

    if not r.ok:
        # Preserve Google's useful error message without echoing the API key.
        try:
            err_data=r.json()
            err_obj=err_data.get("error", {})
            message=err_obj.get("message") or r.text[:1200]
            status=err_obj.get("status") or ""
            code=err_obj.get("code") or r.status_code
            suffix=f" ({status})" if status else ""
            raise RuntimeError(f"Gemini API returned HTTP {code}{suffix}: {message}")
        except ValueError:
            raise RuntimeError(f"Gemini API returned HTTP {r.status_code}: {r.text[:1200]}")

    try:
        data=r.json()
        candidates=data.get("candidates") or []
        if not candidates:
            prompt_feedback=data.get("promptFeedback", {})
            block_reason=prompt_feedback.get("blockReason", "unknown")
            raise RuntimeError(f"Gemini returned no candidates. Prompt block reason: {block_reason}")
        raw=candidates[0]["content"]["parts"][0]["text"]
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Gemini response was not in the expected format: {e}") from e
    result=json.loads(raw)
    clips=result.get("clips",[])
    if len(clips) not in (4,5):
        raise RuntimeError("Gemini did not return exactly 4 or 5 clips; please run again.")
    if any(int(c.get("duration_seconds",0)) != 10 for c in clips):
        raise RuntimeError("Gemini returned a clip duration other than 10 seconds.")
    result["created_at_utc"]=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
    result["job_id"]=uuid.uuid4().hex[:12]
    return result


def save_job(job):
    (JOBS_DIR / f"{job['job_id']}.json").write_text(
        json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
    )

def read_job(job_id):
    p = JOBS_DIR / f"{Path(job_id).name}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def make_outro(story, output_path):
    """Create a simple branded end card; no copyrighted characters or logos."""
    w, h = 720, 1280
    img = Image.new("RGB", (w, h))
    px = img.load()
    top = (21, 32, 58)
    bottom = (76, 37, 94)
    for y in range(h):
        t = y / max(1, h - 1)
        c = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        for x in range(w):
            px[x, y] = c
    draw = ImageDraw.Draw(img)
    font_paths = [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagariUI-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    hindi_font_path = next((p for p in font_paths if Path(p).exists()), None)
    latin_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    def font(path, size):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()
    hindi_font = font(hindi_font_path, 42) if hindi_font_path else font(latin_path, 38)
    latin_font = font(latin_path, 42)
    small_font = font(latin_path, 28)

    # Decorative center panel
    draw.rounded_rectangle((42, 300, 678, 960), radius=38, fill=(255, 255, 255), outline=(255, 220, 140), width=5)
    title = "LIKE  •  SHARE  •  FOLLOW"
    bbox = draw.textbbox((0, 0), title, font=latin_font)
    draw.text(((w - (bbox[2] - bbox[0])) / 2, 430), title, font=latin_font, fill=(35, 42, 70))

    if story.get("format") == "series" and int(story.get("part_number", 1)) < int(story.get("total_parts", 1)):
        next_part = int(story.get("part_number", 1)) + 1
        hindi = f"Part {next_part} देखने के लिए"
        hindi2 = "FOLLOW करें ❤️"
    else:
        hindi = "ऐसी और कहानियों के लिए"
        hindi2 = "FOLLOW करें ❤️"

    for text, y, fnt, fill in [
        (hindi, 570, hindi_font, (48, 54, 82)),
        (hindi2, 650, hindi_font, (195, 55, 80)),
    ]:
        bb = draw.textbbox((0, 0), text, font=fnt)
        draw.text(((w - (bb[2] - bb[0])) / 2, y), text, font=fnt, fill=fill)

    footer = "THANK YOU FOR WATCHING!"
    bb = draw.textbbox((0, 0), footer, font=small_font)
    draw.text(((w - (bb[2] - bb[0])) / 2, 850), footer, font=small_font, fill=(85, 90, 115))
    img.save(output_path, "PNG")


FREE_IMAGE_SOURCE = "Wikimedia Commons (free media; individual file licences vary)"

class BudgetExceeded(RuntimeError):
    pass

def budget_summary():
    return {"provider": "free Wikimedia Commons images + local FFmpeg", "api_spend_inr": 0,
            "monthly_cap_inr": 0, "note": "No paid media API is called by this build."}

def find_animal_keyword(prompt):
    text = (prompt or "").lower()
    animals = ["lion", "tiger", "elephant", "monkey", "fox", "wolf", "bear", "rabbit", "deer", "zebra", "giraffe", "leopard", "cheetah", "crocodile", "snake", "eagle", "owl", "parrot", "panda", "gorilla", "horse", "dog", "cat", "wild boar", "hippo", "rhino"]
    for animal in animals:
        if animal in text:
            return animal
    return "wild animal"

def generate_scene_image(prompt, image_path):
    """Fetch a freely licensed animal photo from Wikimedia Commons; no paid API key."""
    animal = find_animal_keyword(prompt)
    query = f'{animal} animal photograph'
    params = {
        "action": "query", "generator": "search", "gsrsearch": f'filetype:bitmap {query}',
        "gsrnamespace": 6, "gsrlimit": 15, "prop": "imageinfo", "iiprop": "url|extmetadata",
        "iiurlwidth": 900, "format": "json"
    }
    headers = {"User-Agent": "KidsWildAnimalStoriesBot/1.0 (story reel generator)"}
    response = requests.get("https://commons.wikimedia.org/w/api.php", params=params, headers=headers, timeout=45)
    response.raise_for_status()
    pages = (response.json().get("query") or {}).get("pages") or {}
    candidates = list(pages.values())
    if not candidates:
        raise RuntimeError(f"No free Wikimedia image found for {animal}; try another story prompt.")
    # Prefer a result with a usable thumbnail URL.
    page = next((x for x in candidates if (x.get("imageinfo") or [{}])[0].get("thumburl")), None)
    if not page:
        raise RuntimeError(f"Wikimedia returned no downloadable image for {animal}.")
    info = page["imageinfo"][0]
    image_url = info.get("thumburl") or info.get("url")
    img = requests.get(image_url, headers=headers, timeout=90)
    img.raise_for_status()
    image_path.write_bytes(img.content)
    if image_path.stat().st_size < 1000:
        raise RuntimeError("Downloaded Wikimedia image is unexpectedly small.")
    meta = info.get("extmetadata") or {}
    credit = {
        "title": page.get("title", "Wikimedia Commons image"),
        "source_url": info.get("descriptionurl", "https://commons.wikimedia.org/"),
        "artist": (meta.get("Artist") or {}).get("value", "Unknown"),
        "license": (meta.get("LicenseShortName") or {}).get("value", "Check source page")
    }
    return credit

def make_animated_image_clip(image_path, output_path, duration_seconds=10):
    frames = int(duration_seconds * 24)
    vf = (
        f"scale=540:960:force_original_aspect_ratio=increase,crop=540:960,"
        f"zoompan=z='min(zoom+0.00045,1.10)':d={frames}:s=480x854:fps=24,"
        "setsar=1,format=yuv420p"
    )
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
        "-vf", vf, "-t", str(duration_seconds), "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "25",
        "-pix_fmt", "yuv420p", str(output_path)
    ], capture_output=True, text=True, check=True, timeout=300)

def make_video_scene_clip(video_path, output_path, duration_seconds=10):
    vf = (
        "scale=480:854:force_original_aspect_ratio=increase,crop=480:854,fps=24,"
        "tpad=stop_mode=clone:stop_duration=5,trim=duration=10,setpts=PTS-STARTPTS,setsar=1,format=yuv420p"
    )
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path), "-vf", vf, "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "25",
        "-pix_fmt", "yuv420p", str(output_path)
    ], capture_output=True, text=True, check=True, timeout=300)


def make_original_bed_music(path, duration_seconds):
    """Synthesize an original cinematic boom-boom percussion bed; no sampled music."""
    import array, random
    sample_rate = 22050
    total = int(sample_rate * duration_seconds)
    samples = array.array("h")
    rng = random.Random(4127)
    # A low cinematic pulse every ~0.8 sec, with stronger impacts at scene transitions.
    beat_interval = 0.80
    beat_times = [i * beat_interval for i in range(int(duration_seconds / beat_interval) + 1)]
    impact_times = [max(0.0, i * 10.0 - 0.08) for i in range(int(duration_seconds / 10.0) + 1)]
    # Precompute brief noise bursts for snare/impact texture.
    noise_seed = [rng.uniform(-1, 1) for _ in range(int(sample_rate * 0.20))]
    for i in range(total):
        t = i / sample_rate
        val = 0.0

        # Low kick / BOOM: descending sine sweep, 230ms decay.
        for bt in beat_times:
            dt = t - bt
            if 0 <= dt < 0.24:
                freq = 82.0 - 48.0 * (dt / 0.24)
                env = math.exp(-dt * 15.0)
                val += 0.68 * env * math.sin(2 * math.pi * freq * dt)

        # Extra deep impact on every second beat.
        for it in impact_times:
            dt = t - it
            if 0 <= dt < 0.55:
                freq = 58.0 - 36.0 * (dt / 0.55)
                env = math.exp(-dt * 7.0)
                val += 0.55 * env * math.sin(2 * math.pi * freq * dt)

        # Short synthetic snare/clap on offbeats.
        for bt in beat_times:
            dt = t - (bt + beat_interval * 0.5)
            if 0 <= dt < 0.12:
                idx = min(len(noise_seed)-1, int(dt * sample_rate))
                val += 0.12 * math.exp(-dt * 32.0) * noise_seed[idx]

        # Quiet suspense synth pulse underneath.
        val += 0.045 * math.sin(2 * math.pi * 55.0 * t) * (0.65 + 0.35 * math.sin(2 * math.pi * 0.25 * t))
        # Fade edges and soft clipping.
        fade = min(1.0, t / 1.0, max(0.0, (duration_seconds - t) / 1.2))
        val = math.tanh(val * 1.15) * fade * 0.72
        samples.append(int(max(-1.0, min(1.0, val)) * 32767))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())

def create_hindi_voiceover(story, mp3_path):
    text = story.get("full_voiceover_hi") or " ".join(
        c.get("voiceover_hi", "") for c in story.get("clips", [])
    )
    if not text.strip():
        raise RuntimeError("Story pack has no Hindi voiceover text.")
    try:
        from gtts import gTTS
        gTTS(text=text, lang="hi", slow=False).save(str(mp3_path))
        if not mp3_path.exists() or mp3_path.stat().st_size < 1000:
            raise RuntimeError("Hindi TTS returned an empty audio file.")
        return True
    except Exception as e:
        # Fail visibly instead of silently claiming narration exists.
        raise RuntimeError(f"Hindi voiceover generation failed (gTTS network/service): {e}") from e

def make_outro(story, output_path):
    """Create a simple branded end card; no copyrighted characters or logos."""
    w, h = 480, 854
    img = Image.new("RGB", (w, h))
    px = img.load()
    top = (21, 32, 58)
    bottom = (76, 37, 94)
    for y in range(h):
        t = y / max(1, h - 1)
        c = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        for x in range(w):
            px[x, y] = c
    draw = ImageDraw.Draw(img)
    font_paths = [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagariUI-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    hindi_font_path = next((p for p in font_paths if Path(p).exists()), None)
    latin_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    def font(path, size):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()
    hindi_font = font(hindi_font_path, 28) if hindi_font_path else font(latin_path, 24)
    latin_font = font(latin_path, 28)
    small_font = font(latin_path, 18)
    draw.rounded_rectangle((24, 210, 456, 650), radius=28, fill=(255, 255, 255), outline=(255, 220, 140), width=4)
    title = "LIKE  •  SHARE"
    bbox = draw.textbbox((0, 0), title, font=latin_font)
    draw.text(((w - (bbox[2] - bbox[0])) / 2, 290), title, font=latin_font, fill=(35, 42, 70))
    if story.get("format") == "series" and int(story.get("part_number", 1)) < int(story.get("total_parts", 1)):
        hindi = f"Part {int(story.get('part_number',1))+1} देखने के लिए"
        hindi2 = "FOLLOW करें ❤️"
    else:
        hindi = "ऐसी और कहानियों के लिए"
        hindi2 = "FOLLOW करें ❤️"
    for text, y, fnt, fill in [
        (hindi, 405, hindi_font, (48, 54, 82)),
        (hindi2, 475, hindi_font, (195, 55, 80)),
    ]:
        bb = draw.textbbox((0, 0), text, font=fnt)
        draw.text(((w - (bb[2] - bb[0])) / 2, y), text, font=fnt, fill=fill)
    footer = "THANK YOU FOR WATCHING!"
    bb = draw.textbbox((0, 0), footer, font=small_font)
    draw.text(((w - (bb[2] - bb[0])) / 2, 575), footer, font=small_font, fill=(85, 90, 115))
    img.save(output_path, "PNG")

def ffprobe_duration(media_path):
    """Return media duration in seconds using the ffprobe binary installed with FFmpeg."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(media_path)],
            capture_output=True, text=True, check=True, timeout=30
        )
        duration = float(result.stdout.strip())
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("ffprobe returned an invalid duration")
        return duration
    except (subprocess.SubprocessError, ValueError) as exc:
        raise RuntimeError(f"Could not read rendered video duration with ffprobe: {exc}") from exc

def assemble_reel(job_id, story, scene_paths):
    work = JOBS_DIR / job_id
    outro = work / "outro.png"
    make_outro(story, outro)
    concat_file = work / "concat.txt"
    concat_file.write_text(
        "".join("file '" + str(p.resolve()).replace("'", "'\\''") + "'\n" for p in scene_paths),
        encoding="utf-8"
    )
    silent_joined = work / "joined-silent.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "25",
        "-pix_fmt", "yuv420p", "-an", str(silent_joined)
    ], capture_output=True, text=True, check=True, timeout=600)

    duration = ffprobe_duration(silent_joined)
    voice = work / "voiceover-hi.mp3"
    create_hindi_voiceover(story, voice)
    music = work / "original-soft-bed.wav"
    make_original_bed_music(music, duration)
    final_path = OUT_DIR / f"{job_id}-final.mp4"
    start = max(0, duration - 3.5)
    subprocess.run([
        "ffmpeg", "-y", "-i", str(silent_joined), "-loop", "1", "-i", str(outro),
        "-i", str(voice), "-i", str(music),
        "-filter_complex",
        f"[1:v]scale=480:854[card];[0:v][card]overlay=0:0:enable='gte(t,{start:.3f})'[v];"
        "[2:a]volume=1.0[narr];[3:a]volume=0.24[bg];"
        "[narr][bg]amix=inputs=2:duration=longest:dropout_transition=2[a]",
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "25", "-c:a", "aac", "-b:a", "96k", "-shortest",
        "-movflags", "+faststart", str(final_path)
    ], capture_output=True, text=True, check=True, timeout=600)
    return final_path

def video_worker(job_id, story):
    job = read_job(job_id) or {"job_id": job_id}
    job.update({"video_status": "generating", "video_progress": 0, "video_error": None,
                "provider": "Free Wikimedia Commons images + FFmpeg", "quality": "480p",
                "ai_video_clips": 0, "paid_api_calls": 0})
    save_job(job)
    try:
        clips = story.get("clips", [])
        if len(clips) < 2:
            raise RuntimeError("At least two story scenes are required.")
        work = JOBS_DIR / job_id
        work.mkdir(parents=True, exist_ok=True)
        scene_paths = []
        credits = []
        for index, clip in enumerate(clips, start=1):
            image_path = work / f"scene-{index:02d}.jpg"
            prompt = clip.get("visual_prompt", "") + "\nAction: " + clip.get("action", "")
            credit = generate_scene_image(prompt, image_path)
            credits.append(credit)
            scene_clip = work / f"scene-{index:02d}.mp4"
            make_animated_image_clip(image_path, scene_clip, 10)
            scene_paths.append(scene_clip)
            job["video_progress"] = int(index * 100 / len(clips))
            job["video_completed_scenes"] = index
            save_job(job)
        final_path = assemble_reel(job_id, story, scene_paths)
        (OUT_DIR / f"{job_id}-image-credits.json").write_text(json.dumps(credits, ensure_ascii=False, indent=2), encoding="utf-8")
        job.update({"video_status": "completed", "video_progress": 100,
                    "video_url": f"/media/{final_path.name}", "video_filename": final_path.name,
                    "image_source": FREE_IMAGE_SOURCE, "image_credits_file": f"/media/{job_id}-image-credits.json",
                    "budget": budget_summary()})
        save_job(job)
    except Exception as e:
        job.update({"video_status": "failed", "video_error": str(e)[:1800], "budget": budget_summary()})
        save_job(job)

def start_video_job(job_id, story):
    job = read_job(job_id) or {"job_id": job_id}
    if job.get("video_status") in ("queued", "generating", "completed"):
        return
    job.update({"video_status": "queued", "video_progress": 0, "video_error": None})
    save_job(job)
    threading.Thread(target=video_worker, args=(job_id, story), daemon=True).start()

def load_recent_titles():
    p=OUT_DIR/"recent_titles.json"
    if not p.exists(): return []
    try: return json.loads(p.read_text(encoding="utf-8"))[-12:]
    except Exception: return []

def save_story(story):
    p=OUT_DIR/f"{story['job_id']}-story-pack.json"
    p.write_text(json.dumps(story,ensure_ascii=False,indent=2),encoding="utf-8")
    recent=load_recent_titles()
    recent.append(story.get("series_title",""))
    (OUT_DIR/"recent_titles.json").write_text(json.dumps(recent[-12:],ensure_ascii=False),encoding="utf-8")
    latest=OUT_DIR/"latest.json"
    latest.write_text(json.dumps(story,ensure_ascii=False,indent=2),encoding="utf-8")
    return p


# --- Google Flow browser controller (user-authorized UI automation) ---
FLOW_SCREENSHOT = OUT_DIR / "flow-browser.png"

def require_run_token(credentials):
    token = env("RUN_TOKEN")
    supplied = credentials.credentials if credentials else ""
    if not token or supplied != token:
        raise HTTPException(status_code=401, detail="Unauthorized")

class FlowClickRequest(BaseModel):
    x: int = Field(ge=0, le=5000)
    y: int = Field(ge=0, le=5000)
class FlowTypeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
class FlowKeyRequest(BaseModel):
    key: str = Field(min_length=1, max_length=40)
class FlowPromptRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)

def flow_controller():
    try:
        import flow_controller as controller
        return controller
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Flow browser controller unavailable: {exc}")

@app.get("/flow/status")
def flow_status(credentials: HTTPAuthorizationCredentials = Depends(run_auth)):
    require_run_token(credentials)
    return flow_controller().status()

@app.post("/flow/start")
def flow_start(credentials: HTTPAuthorizationCredentials = Depends(run_auth)):
    require_run_token(credentials)
    if env("FLOW_AUTOMATION_ENABLED", "true").lower() not in ("1", "true", "yes", "on"):
        raise HTTPException(status_code=403, detail="Set FLOW_AUTOMATION_ENABLED=true in Railway Variables.")
    try:
        result = flow_controller().start_browser()
        return {**result, "screenshot_url": "/flow/screenshot",
                "next_step": "Open /flow/screenshot, then sign in yourself if Google asks. Do not share passwords or cookies."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not start Flow browser: {exc}")

@app.get("/flow/screenshot")
def flow_screenshot(credentials: HTTPAuthorizationCredentials = Depends(run_auth)):
    require_run_token(credentials)
    try:
        flow_controller().screenshot(FLOW_SCREENSHOT)
        return FileResponse(FLOW_SCREENSHOT, media_type="image/png", filename="flow-browser.png")
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc))

@app.post("/flow/click")
def flow_click(payload: FlowClickRequest, credentials: HTTPAuthorizationCredentials = Depends(run_auth)):
    require_run_token(credentials)
    try: return flow_controller().click(payload.x, payload.y)
    except Exception as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.post("/flow/type")
def flow_type(payload: FlowTypeRequest, credentials: HTTPAuthorizationCredentials = Depends(run_auth)):
    require_run_token(credentials)
    try: return flow_controller().type_text(payload.text)
    except Exception as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.post("/flow/press")
def flow_press(payload: FlowKeyRequest, credentials: HTTPAuthorizationCredentials = Depends(run_auth)):
    require_run_token(credentials)
    try: return flow_controller().press_key(payload.key)
    except Exception as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.post("/flow/fill-prompt")
def flow_fill_prompt(payload: FlowPromptRequest, credentials: HTTPAuthorizationCredentials = Depends(run_auth)):
    require_run_token(credentials)
    try: return flow_controller().fill_prompt(payload.prompt)
    except Exception as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.post("/flow/stop")
def flow_stop(credentials: HTTPAuthorizationCredentials = Depends(run_auth)):
    require_run_token(credentials)
    try: return flow_controller().close_browser()
    except Exception as exc: raise HTTPException(status_code=500, detail=str(exc))

@app.get("/")
def home():
    return {"name":"Kids Wild Animal Stories","status":"online",
            "mode":"Free Wikimedia Commons animal images + animated scenes + Hindi voiceover + original boom music + auto-join + CTA",
            "video_generation_enabled": True,
            "media_api_budget": budget_summary(),
            "target":"3 story packs per day", "flow_browser_controller": True}

@app.get("/health")
def health(): return {"ok":True}

@app.post("/run")
def run_now(credentials: HTTPAuthorizationCredentials = Depends(run_auth)):
    token=env("RUN_TOKEN")
    supplied = credentials.credentials if credentials else ""
    if not token or supplied != token:
        raise HTTPException(status_code=401,detail="Unauthorized")
    try:
        story=gemini_story()
        path=save_story(story)
        job = {
            "job_id": story["job_id"],
            "story_pack": f"/media/{path.name}",
            "video_status": "disabled",
            "video_progress": 0,
            "video_error": None
        }
        save_job(job)
        video_enabled = True
        if video_enabled:
            start_video_job(story["job_id"], story)
            video_status = "queued"
            note = "Story created. Free image-based Reel rendering has started. Check /status/{job_id}. No fal.ai key or deposit is needed."
        else:
            video_status = "disabled"
            note = "Story pack created; free image-based Reel rendering is enabled."
        return JSONResponse({
            "ok":True,"job_id":story["job_id"],
            "format":story["format"],"series_title":story["series_title"],
            "part_number":story["part_number"],"total_parts":story["total_parts"],
            "clip_count":len(story["clips"]),
            "story_pack":f"/media/{path.name}",
            "video_status":video_status,
            "status_url":f"/status/{story['job_id']}",
            "note":note,
            "budget": budget_summary()
        })
    except Exception as e:
        raise HTTPException(status_code=500,detail=str(e))

@app.get("/status/{job_id}")
def job_status(job_id: str):
    job = read_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job

@app.post("/generate-video/{job_id}")
def generate_video_for_job(job_id: str, credentials: HTTPAuthorizationCredentials = Depends(run_auth)):
    token=env("RUN_TOKEN")
    supplied = credentials.credentials if credentials else ""
    if not token or supplied != token:
        raise HTTPException(status_code=401,detail="Unauthorized")
    job = read_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    
    story_path = OUT_DIR / f"{Path(job_id).name}-story-pack.json"
    if not story_path.is_file():
        raise HTTPException(status_code=404, detail="Story pack not found.")
    story = json.loads(story_path.read_text(encoding="utf-8"))
    start_video_job(job_id, story)
    return {"ok": True, "job_id": job_id, "video_status": "queued", "status_url": f"/status/{job_id}"}

@app.get("/budget")
def budget_status():
    return budget_summary()

@app.get("/latest")
def latest():
    p=OUT_DIR/"latest.json"
    if not p.exists(): return {"status":"No story pack generated yet."}
    return json.loads(p.read_text(encoding="utf-8"))

@app.get("/media/{filename}")
def media(filename:str):
    safe=Path(filename).name
    p=OUT_DIR/safe
    if not p.is_file(): raise HTTPException(status_code=404,detail="File not found.")
    if safe.endswith(".json"):
        return JSONResponse(json.loads(p.read_text(encoding="utf-8")))
    if safe.endswith(".mp4"):
        return FileResponse(p, media_type="video/mp4", filename=safe)
    raise HTTPException(status_code=415, detail="Unsupported file type.")
