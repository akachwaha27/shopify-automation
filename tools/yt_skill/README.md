Tools from [youtube-agent-skill](https://github.com/Jakeschincariol/youtube-agent-skill) by Jake Schincariol (MIT, see LICENSE).
- hookscore.py + hooks.json: score opening lines against 21 hook formulas
- title.py: lint a title + thumbnail-text pairing
- swipe.py: rank videos by how far each beat its own channel's median
- chapters.py: chapter boundaries from a transcript (yt-chapters)
- deadair.py: dead air / filler / retake finder for a timestamped transcript (yt-edit)
- retention.py: read a YouTube Studio audience-retention export (yt-retention)
Only change: swipe.py reads hooks.json from this folder.
