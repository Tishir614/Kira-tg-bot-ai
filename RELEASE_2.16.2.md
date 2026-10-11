# KiraBot 2.16.2 Image diagnostics

- Failed image requests now say why: the user sees each provider's reason (AI Horde / Perchance / ComfyUI) instead of a generic "try later".
- `/image_health` (проверка_картинок), owner/sudo only: probes AI Horde (reachability and which furry models have live workers), Perchance (user key) and ComfyUI, with timings, and tells what to check.
- AI Horde falls back to general models (`HORDE_FALLBACK_MODELS`, default Deliberate, Dreamshaper, Anything Diffusion, stable_diffusion) when no furry-trained model has a live worker; the used model is shown in the caption.
- masturbate and alcohol modules untouched.
