from pathlib import Path
p=Path('/mnt/data/freebuild/app.py')
s=p.read_text(encoding='utf-8')
# replace fal constants + budget functions through fal download helpers with free metadata
start=s.index('FAL_VIDEO_ENDPOINT =')
end=s.index('def make_animated_image_clip(')
replacement='''FREE_IMAGE_SOURCE = "Wikimedia Commons (free media; individual file licences vary)"

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

'''
s=s[:start]+replacement+s[end:]
# Replace video worker
start=s.index('def video_worker(job_id, story):')
end=s.index('\ndef start_video_job(', start)
worker='''def video_worker(job_id, story):
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
            prompt = clip.get("visual_prompt", "") + "\\nAction: " + clip.get("action", "")
            credit = generate_scene_image(prompt, image_path)
            credits.append(credit)
            scene_clip = work / f"scene-{index:02d}.mp4"
            make_animated_image_clip(image_path, scene_clip, 10)
            scene_paths.append(scene_clip)
            job["video_progress"] = int(index * 100 / len(clips))
            job["video_completed_scenes"] = index
            save_job(job)
        final_path = assemble_reel(job_id, story, scene_paths)
        (work / "image-credits.json").write_text(json.dumps(credits, ensure_ascii=False, indent=2), encoding="utf-8")
        job.update({"video_status": "completed", "video_progress": 100,
                    "video_url": f"/media/{final_path.name}", "video_filename": final_path.name,
                    "image_source": FREE_IMAGE_SOURCE, "image_credits_file": f"/media/{job_id}/image-credits.json",
                    "budget": budget_summary()})
        save_job(job)
    except Exception as e:
        job.update({"video_status": "failed", "video_error": str(e)[:1800], "budget": budget_summary()})
        save_job(job)
'''
s=s[:start]+worker+s[end:]
# Replace home mode/status and run notes, endpoint checks
s=s.replace('"mode":"fal Wan 2.2 Fast 480p + animated FLUX stills + Hindi voiceover + auto-join + CTA",','"mode":"Free Wikimedia Commons animal images + animated scenes + Hindi voiceover + original boom music + auto-join + CTA",')
s=s.replace('"video_generation_enabled": env("ENABLE_VIDEO_GENERATION", "true").lower() == "true",','"video_generation_enabled": True,')
s=s.replace('"fal_budget": budget_summary(),','"media_api_budget": budget_summary(),')
s=s.replace('video_enabled = env("ENABLE_VIDEO_GENERATION", "true").lower() == "true"','video_enabled = True')
s=s.replace('note = "Story created. Automatic video generation has started in the background. Check /status/{job_id}."','note = "Story created. Free image-based Reel rendering has started. Check /status/{job_id}. No fal.ai key or deposit is needed."')
s=s.replace('note = "Story pack created. Set ENABLE_VIDEO_GENERATION=true only after reviewing paid video-generation costs to create clips, join them, and add the CTA end card."','note = "Story pack created; free image-based Reel rendering is enabled."')
s=s.replace('if env("ENABLE_VIDEO_GENERATION", "false").lower() != "true":\n        raise HTTPException(status_code=403, detail="Video generation is disabled. Set ENABLE_VIDEO_GENERATION=true after reviewing costs.")','')
p.write_text(s,encoding='utf-8')
