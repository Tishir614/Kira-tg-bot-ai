# KiraBot 1.5.0 — Full audit + ComfyUI image backend

- Replaced the fragile stable-diffusion.cpp wrapper with ComfyUI v0.36.0.
- Default local checkpoint is DreamShaper 8 pruned safetensors (2.13 GB).
- Image workflow uses only stock ComfyUI nodes: CheckpointLoaderSimple, CLIPTextEncode, EmptyLatentImage, KSampler, VAEDecode, SaveImage.
- Existing `/image` and Kira-avatar call sites keep the same Python interface.
- Added ComfyUI health reporting and bounded generation timeouts.
- Preserved all persistent Kira/Redis/Ollama/STT/SketchForge volumes during upgrade.
- Refreshed Docker helper images and selected Python dependency floors without crossing breaking major versions.
