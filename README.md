# code-foundry

The daily coding streak continues here. One small, real program
every day, picking up at Day 14 (Days 1-13 live in cpp-foundry and
py-foundry). No filler commits, no empty files.

## Day 14 - Smart File Organizer (Python)

`day-14-file-organizer/organizer.py`

Sorts the loose files in a folder into category subfolders by
extension: Images, Documents, Audio, Video, Archives, Code, and
Other for anything unrecognized. It never overwrites: a name that
is already taken gets `_1`, `_2`, and so on appended. Every move is
recorded in a JSON undo log (`.organizer_undo.json`), so a run can
be fully reversed with `--undo`. Preview everything first with
`--dry-run`, and add `--recursive` to also sort files inside
subfolders. Stdlib only, no dependencies.

How to run:

```
python3 organizer.py ~/Downloads
python3 organizer.py ~/Downloads --dry-run
python3 organizer.py ~/Downloads --recursive
python3 organizer.py ~/Downloads --undo
```

Example:

```
moved: backup.zip -> Archives/backup.zip
moved: notes.txt -> Documents/notes.txt
moved: photo.jpg -> Images/photo.jpg
moved: song.mp3 -> Audio/song.mp3

Organized 4 file(s):
  Archives: 1
  Audio: 1
  Documents: 1
  Images: 1
```
