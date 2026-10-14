# Adding sample videos

Keep tutorial videos out of Git because recordings can be large and may contain
private information. For a local manual check, place a 5–10 minute English
terminal/IDE recording in this directory, run `python -m pipeline.run
samples/your-video.mp4`, then delete it when finished. Automated tests use
generated data and do not need a sample recording or network access.
