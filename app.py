import sys
from pathlib import Path

# Add src and component directories to Python path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
components_dir = ROOT / "components"
if components_dir.is_dir():
    for comp in components_dir.iterdir():
        if comp.is_dir():
            sys.path.insert(0, str(comp))

import uvicorn
from marketpulse.api.app import create_app

app = create_app()

# If running inside a Hugging Face Gradio space, mount Gradio on /_hf for healthchecks
try:
    import gradio as gr
    app = gr.mount_gradio_app(app, gr.Blocks(title="MarketPulse AI"), path="/_hf")
except Exception:
    pass

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
