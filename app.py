"""Streamlit interface for turning one screen recording into a tutorial."""

from __future__ import annotations

from pathlib import Path
import tempfile

import streamlit as st

from pipeline.run import run_pipeline


def main() -> None:
    """Render the upload, progress, Markdown preview, and download flow."""
    st.set_page_config(page_title="Screen2Tutorial", page_icon="🎬", layout="wide")
    st.title("Screen2Tutorial")
    st.write(
        "Turn a coding screen recording into a code-backed, step-by-step Markdown tutorial. "
        "Speech and screen text ground the explanation; shell commands are checked against the recording."
    )
    uploaded = st.file_uploader("Upload a 5–10 minute recording", type=["mp4", "mov", "mkv", "webm", "avi"])
    if uploaded is None:
        st.info("Upload a single-speaker English terminal or IDE tutorial to begin.")
        st.caption("Code examples are transcribed from video frames; review unclear OCR characters before publishing.")
        return
    if st.button("Generate tutorial", type="primary"):
        config_path = Path(__file__).parent / "config.yaml"
        progress_bar = st.progress(0, text="Preparing pipeline")
        stages = [
            "Extracting audio and frames", "Transcribing speech", "Reading screen text",
            "Aligning transcript and screen text", "Writing tutorial steps",
            "Verifying commands", "Rendering Markdown",
        ]
        current = {"index": 0}

        def update_progress(stage: str) -> None:
            """Advance the upload progress indicator when a stage begins."""
            current["index"] = stages.index(stage) if stage in stages else current["index"]
            progress_bar.progress((current["index"] + 1) / len(stages), text=stage)

        try:
            # Keep the uploaded recording on the same writable volume as the
            # app. Some Windows-managed environments deny access to the
            # default system temp directory, including during cleanup.
            temp_root = config_path.parent / ".tmp"
            temp_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="screen2tutorial-", dir=temp_root) as temp_dir:
                video_path = Path(temp_dir) / Path(uploaded.name).name
                video_path.write_bytes(uploaded.getvalue())
                result = run_pipeline(video_path, config_path, update_progress)
            progress_bar.progress(1.0, text="Tutorial ready")
            st.markdown(result.markdown)
            st.download_button(
                "Download Markdown",
                data=result.markdown.encode("utf-8"),
                file_name="tutorial.md",
                mime="text/markdown",
            )
            with st.expander("Stage timings"):
                st.json(result.timings)
        except Exception as exc:
            progress_bar.empty()
            st.error(str(exc))


if __name__ == "__main__":
    main()
