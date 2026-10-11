from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_comfyui_replaced_old_backend():
    compose=(ROOT/'compose.yml').read_text()
    image=(ROOT/'bot/image_generation.py').read_text()
    assert '  comfyui:' in compose
    assert 'http://comfyui:8188' in compose
    assert '/prompt' in image and '/history/' in image and '/view' in image
    assert 'CheckpointLoaderSimple' in image and 'KSampler' in image
    assert not (ROOT/'deploy/local-image').exists()

def test_comfyui_is_pinned_and_model_is_safetensors():
    docker=(ROOT/'deploy/comfyui/Dockerfile').read_text()
    compose=(ROOT/'compose.yml').read_text()
    assert 'COMFYUI_VERSION=v0.36.0' in docker
    assert 'DreamShaper_8_pruned.safetensors' in compose
