# Media Nest

**Media Nest** is a powerful local media manager and viewer for browsing, tagging, and enjoying your collection of images, GIFs, videos, manga, and manhwa — all from one clean, dark-themed app.

---

## Table of Contents

- [Getting Started](#getting-started)
- [Main Layout](#main-layout)
- [Sidebar Buttons](#sidebar-buttons)
- [File Tree](#file-tree)
- [Tag Panel](#tag-panel)
- [Gallery](#gallery)
- [Image Viewer](#image-viewer)
- [Video Player](#video-player)
- [Manga & Manhwa Reader](#manga--manhwa-reader)
- [Database & Tag Search](#database--tag-search)
- [Terminal](#terminal)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Right-Click Menu](#right-click-menu)
- [Settings Dialog](#settings-dialog)
  - [Database Tab](#database-tab)
  - [Interface Tab](#interface-tab)
  - [Tag Manager Tab](#tag-manager-tab)
  - [Image Dedup Tab](#image-dedup-tab)
  - [Video Dedup Tab](#video-dedup-tab)
  - [Pagination Tab](#pagination-tab)
- [Supported Formats](#supported-formats)

---

## Getting Started

When you first launch the app, a **Welcome Setup** window will appear, asking how you want to set up your workspace:
- **Link Kemono Downloader Database**: If you already use *Kemono Downloader*, this connects to your existing `library.db` so you immediately share its tags and data.
- **Create Portable Database**: If you are starting fresh, this creates a standalone database inside the app's folder.

Both options will automatically attempt to download the `character.db` asset from the cloud for you.

Once set up, the main window will open. It is split into two areas — a **sidebar** on the left for browsing, and a **viewer + gallery** on the right for viewing your media. To begin, click **OPEN FOLDER** or drag a folder straight onto the window.

---

## Main Layout

The window is divided into two main panels:

- **Left — Sidebar**: Contains the logo, action buttons, search bar, file tree, and tag panel.
- **Right — Viewer & Gallery**: The top area shows your selected media (image, video, or reader), and the bottom strip shows thumbnail previews of the current folder.

Both panels are **resizable** — drag the divider between them to adjust.

---

## Sidebar Buttons

### <img src="assets/uisvg/folder.svg" width="20" height="20" align="top"> OPEN FOLDER
Opens a folder from your computer and loads it into the file tree. You can open multiple folders at once — each appears as its own entry. You can also **drag and drop** a folder directly onto the window instead.

---

### <img src="assets/uisvg/database.svg" width="20" height="20" align="top"> LOAD DB / DB ACTIVE
Connects the app to your media library database, which enables tag-based searching.

- When **inactive** (green): Click to connect. If it's your first time, a setup window will guide you to select your database folder.
- When **active** (purple, labeled "DB ACTIVE"): Click again to disconnect. This clears the search results, gallery, and file tree back to a clean state.

Once connected, the search bar gains tag autocomplete and the app can search your entire library instantly.

---

### <img src="assets/uisvg/settings.svg" width="20" height="20" align="top"> Settings (Gear Icon)
Opens the Settings window where you can:
- Change the database folder location.
- Adjust the **performance mode** (Low / Balanced / High) which controls how fast thumbnails are generated.

---

### ⧉ Detach Viewer
Pops the media viewer out into a **separate window** — great for multi-monitor setups where you want to browse on one screen and watch on another. Click it again (or close the floating window) to bring the viewer back.

---

### <img src="assets/uisvg/heart.svg" width="20" height="20" align="top"> Support
Opens the **Support & Community** window. Here you'll find quick links to:
- **Contribute Financially**: Ko-fi, Patreon, and Buy Me a Coffee.
- **Get Help & Connect**: GitHub (report issues), Discord (join the server), and Instagram.

---

### <img src="assets/uisvg/search.svg" width="20" height="20" align="top"> Search Bar
Located below the buttons. How it works depends on your mode:

- **Without a database**: Instantly filters the file tree as you type — matches file names, folder names, or file extensions.
- **With a database connected**: Searches your entire media library by tags. Supports multi-tag and AND/OR logic (see [Database & Tag Search](#database--tag-search)). As you type, tag suggestions appear in a dropdown.

---

## File Tree

The left panel shows your loaded folders in a collapsible tree.

- **Click a folder** to expand it and load its contents into the gallery below.
- **Click a file** to open it directly in the viewer. The gallery will also update to show the file's folder.
- **Folder toggle button**: Each folder with subfolders has a small icon on its right edge. Clicking it switches between two modes:
  - **Normal view** — shows only the direct contents of that folder.
  - **Flat / Scan view** — recursively scans all subfolders and shows every media file inside, streamed in as it's found. A scanning indicator appears while it loads.
- **Right-click** anywhere in the tree for file options (copy, cut, paste, delete, etc.).

---

## Tag Panel

Appears at the bottom of the sidebar when you have a database connected and the selected file has tags assigned to it.

| Control | What it does |
|---|---|
| **Tag list** | Shows all tags for the selected file as clickable chips. You can select multiple tags at once. |
| **Search box** (top right of panel) | Filters the displayed tags as you type — useful when a file has many tags. |
| **Eye / toggle button** | Hides or shows the tag list to save space. |
| **"Add tag..." input** | Type a new tag name here and press Enter or click the <img src="assets/uisvg/add.svg" width="16" height="16"> button to add it. |
| **<img src="assets/uisvg/add.svg" width="16" height="16"> Add button** | Saves the typed tag to the selected file in the database. |
| **<img src="assets/uisvg/remove.svg" width="16" height="16"> Delete button** | Removes the selected tag(s) from the file. Select multiple tags to delete them all at once. |

Tags are always saved in lowercase with underscores instead of spaces (e.g., `my_tag`).

---

## Gallery

The bottom strip on the right side shows thumbnail previews of all files in the current folder or search result.

### Gallery Header Bar

The gallery has a slim header bar with the following controls:

| Control | What it does |
|---|---|
| **"Gallery Grid" label** | Section title |
| **Filter by name...** input | Type any text to instantly hide thumbnails that don't match the filename. Clears when you clear the field. |
| **All / Images / Videos** dropdown | Quickly filter the gallery to show only images, only videos, or everything. Each option has an icon. |
| **Size toggle button** | Cycles through three thumbnail sizes — Large → Medium → Small → Large. The icon on the button reflects the current size. |

### Thumbnail Sizes

Click the size toggle button to switch between:

| Mode | Use case |
|---|---|
| **Large** (default) | Best for browsing — big, clear previews |
| **Medium** | A balance between detail and density |
| **Small** | Fit many more items on screen at once |

The size switches instantly without reloading anything.

### Thumbnails

- **Click a thumbnail** to open that file in the viewer above.
- Thumbnails load in the background automatically — a <img src="assets/uisvg/loading.svg" width="16" height="16"> icon shows while they're being generated. Generated thumbnails are cached so they load instantly on your next visit.
- **Gallery folders** (manga/manhwa) show a "stacked pages" style thumbnail.
- **Video thumbnails** are captured from a moment partway through the video, with a <img src="assets/Svg/play.svg" width="16" height="16"> icon overlay.
- Each thumbnail shows the filename beneath it, trimmed if too long.
- **Infinite scroll**: When searching with a database, scrolling to the bottom of the gallery automatically loads more results.
- **Right-click** any thumbnail for file options.

---

## Image Viewer

When you open an image, it fills the viewer area and scales automatically to fit — no matter how you resize the window or drag the splitter.

### Zooming

| Action | Effect |
|---|---|
| **Double-click** the image | Zooms to full (original) resolution, centered on where you clicked |
| **Double-click again** | Returns to fit-to-view |
| `Ctrl + Mouse Wheel` | Zooms in or out centered on the mouse cursor |
| `Ctrl++` or `Ctrl+=` | Zoom in |
| `Ctrl+-` | Zoom out |
| Zoom range | 10% – 1000% |

A small **zoom toolbar** appears in the top-right corner of the viewer when zoomed, showing the current percentage and `−`, `+`, `Reset` buttons. It disappears after a few seconds.

### GIFs
Animated GIFs play automatically and scale with the viewer just like regular images.

### Tall / Strip Images (Manhwa)
If an image is very tall (typical of manhwa or webtoon strips), the app **automatically switches** to the Manhwa Reader mode for a better reading experience instead of the standard image view.

---

## Video Player

Opening a video file reveals the player with a full set of controls below the video.

### Controls

| Control | What it does |
|---|---|
| **Progress bar** | Shows playback position. Click anywhere on it to jump directly to that point. |
| **Current / Total time** | Displays position and total duration. |
| **Volume button** | Click to mute/unmute. The icon changes to reflect the current level. |
| **Volume slider** | Drag to adjust audio level (0–100%). |
| **<img src="assets/Svg/previous.svg" width="16" height="16"> Previous** | Jump to the previous file in the gallery. |
| **<img src="assets/Svg/back%2010Sec.svg" width="16" height="16"> Skip Back 10s** | Rewind 10 seconds. |
| **<img src="assets/Svg/play.svg" width="16" height="16"> / <img src="assets/Svg/pause.svg" width="16" height="16"> Play/Pause** | Toggle playback. |
| **<img src="assets/Svg/skip%2010Sec.svg" width="16" height="16"> Skip Forward 10s** | Fast-forward 10 seconds. |
| **<img src="assets/Svg/next.svg" width="16" height="16"> Next** | Jump to the next file in the gallery. |
| **<img src="assets/Svg/repeat.svg" width="16" height="16"> Loop** | Toggle repeat. When on, the video restarts automatically when it ends. |
| **<img src="assets/Svg/fullscreen.svg" width="16" height="16"> Fullscreen** | Expand the video to fill the entire screen. |

### Fullscreen
- The controls bar **auto-hides** after 3 seconds in fullscreen. Move the mouse to bring it back.
- Press **Escape** or double-click the video to exit fullscreen.

---

## Manga & Manhwa Reader

### Manga Reader

Activated when you open a folder from the gallery. Displays one page at a time in a clean dark reader.

**Navigation toolbar** (at the bottom of the reader):

| Control | What it does |
|---|---|
| **< Prev** button | Go to the previous page |
| **Page number input** | Shows the current page number. Type any page number and press Enter to jump directly to it. |
| **/ Total label** | Shows the total number of pages (e.g., `/ 42`) |
| **Next >** button | Go to the next page |

**Additional navigation:**
- **Click the left half** of the page image to go to the previous page.
- **Click the right half** of the page image to go to the next page.
- Use **Left / Right arrow keys** to navigate pages.
- **Double-click** the image to zoom to full resolution, then double-click again to return to fit view. All the same zoom controls as the image viewer work here (`Ctrl+Wheel`, `Ctrl++`, `Ctrl+-`).

Pages are **sorted naturally** by filename (so `page2` comes before `page10`, not after `page19`).

---

### Manhwa / Webtoon Reader

Activated automatically when an image is very tall (typical of manhwa or webtoon strips), or when a folder of strip-style images is opened.

- All pages are laid out as a **single continuous vertical scroll** — no page-by-page clicking needed.
- Images load **on demand** as you scroll — only what's visible (plus a few pages ahead) is loaded at a time, keeping memory usage low even for very long chapters.
- When you open a specific image from within a folder, the reader automatically **scrolls to that image's position**.
- A **zoom slider** on the right edge of the viewer lets you make the images wider or narrower (50%–200%). Adjusting it clears and re-renders images at the new size instantly.
- The reader **adapts when you resize** the window — images reflow to fit the new width automatically.
- Pages are sorted naturally by filename, same as the manga reader.

---

## Database & Tag Search

When a database is connected, the search bar becomes a powerful tag-based search engine.

### Tag Search Syntax

| You type | What it finds |
|---|---|
| `cat` | Files tagged with `cat` |
| `cat, dog` | Files tagged with **both** `cat` AND `dog` |
| `cat, ~dog` | Files tagged with `cat`, and optionally `dog` |
| `~cat, ~dog` | Files tagged with `cat` **OR** `dog` (at least one) |

- Tags are case-insensitive.
- As you type, the app suggests matching tags from your library.
- After a comma, the autocomplete continues for the next tag — just keep typing.
- Results show in the gallery as thumbnails and are also organized in the file tree by folder.
- Scroll to the bottom of the gallery to load more results automatically.

### Natural Language Smart Search

If you want to search using plain English instead of manually separating tags, prefix your search with `Search: ` (e.g., `Search: makima wearing a suit in an office`). 

The smart search engine will parse your sentence, remove filler words, and automatically map the remaining terms to the closest matching tags in your database using an intelligent bigram-first algorithm. 

**Smart Tag Classification:**
- When parsing, it detects if a matched tag is a **character, series, or artist**. These are treated as **anchor tags** and become strictly required in the image.
- Backgrounds, clothing, and objects (like "beach" or "bikini") are treated as **general tags**.
- If a character anchor is present, all general tags are pooled together and the engine requires the image to match **at least one** of them. This allows the search to be extremely flexible (e.g., returning images with Makima and a suit, or Makima and an office).
- If no character anchor is present in your sentence, the algorithm adapts and strictly requires all general tags so you still get highly precise results.

---

## Terminal

Media Nest includes a built-in terminal that can be opened by clicking the <img src="assets/uisvg/terminal.svg" width="16" height="16"> **Terminal** button in the sidebar. This provides a command-line interface for advanced database manipulation and batch processing without needing external DB tools.

**Available Commands:**
- `tag list`: Shows all unique tags in the database.
- `tag add <tag> <hash1,hash2>`: Manually add a tag to specific file hashes.
- `tag rm <tag> <hash1,hash2>`: Remove a tag from specific files.
- `tag replace <old> <new>`: Globally replace one tag with another (merges them if the new one already exists).
- `tag rename <old> <new>`: Rename a tag globally.
- `tag smartsearch <query>`: Test the NLP tagging engine's parsing logic.
- `file move --from <old_path> --to <new_path>`: Safely update file paths in the database if you moved them outside the app.
- `file delete --orphans`: Purges database records for files that no longer exist on your disk.
- `help` / `clear` / `exit`: Standard terminal commands.

*Tip: Use the `Up` and `Down` arrow keys to cycle through your command history.*

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Space` | Play / Pause video |
| `Left Arrow` | Previous file in gallery (or rewind 10s when video is focused) |
| `Right Arrow` | Next file in gallery (or skip 10s when video is focused) |
| `Escape` | Exit fullscreen |
| `Double-click video` | Toggle fullscreen |
| `Double-click image` | Toggle zoom to full resolution |
| `Ctrl + Mouse Wheel` | Zoom image in/out |
| `Ctrl++` / `Ctrl+=` | Zoom in |
| `Ctrl+-` | Zoom out |
| `Ctrl+C` | Copy selected file |
| `Ctrl+X` | Cut selected file |
| `Ctrl+V` | Paste file into current folder |
| `Delete` | Delete selected file |
| `Enter` (in search bar) | Search immediately |

---

## Right-Click Menu

Right-clicking any file in the **gallery** or **file tree** opens a context menu with standard file operations like copy, cut, paste, rename, delete, and more.

- **File Info**: Click this option to reveal a detailed information panel about the selected file, including resolution, duration, file size, and exact path.

> **Note:** You cannot paste files into database search results — you must be viewing a real folder first.

---

## Settings Dialog

Opened by clicking the <img src="assets/uisvg/settings.svg" width="16" height="16"> gear button in the sidebar. The Settings window is a full-featured multi-tab dialog (minimum 1100×700, resizable and maximizable).

Each tab loads on-demand — tabs that require a database will prompt you to set one up if none is configured.

---

### Database Tab

The first tab. Lets you change the folder where your `library.db` library file lives.

| Control | What it does |
|---|---|
| **Library Folder** input | Shows the current database folder path |
| **Browse...** button | Opens a folder picker to select a new location |
| **Download 1.6M Tags DB** button | Downloads `AllTags.db` from Hugging Face into your app data folder. This is a massive, optional database containing over 1.6 million globally known tags (character names, artists, series). Once downloaded, it runs in a background thread to instantly provide advanced tag autocomplete suggestions anywhere in the app (Search Bar, Tag Manager, Pagination Tab) without freezing the UI. |

#### Database Repair

This section helps you fix your library when files have been **moved, renamed, or are missing** from disk. It scans your drive(s) to find where the files went and then updates your database — or moves the files back — so everything is in sync again.

The Database Repair area is split into two panels side by side:

**Left panel — Scan Log**: A color-coded console that shows every step of the scan in real time:
- 🔵 Blue = scan progress messages
- 🟢 Green = successfully found/relocated files
- 🟡 Orange = warnings (e.g., file found but hash doesn't match)
- 🔴 Red = files that couldn't be located anywhere

**Right panel** (split vertically):
- **Top — Relocated Files table**: Files the scan found at a new location
- **Bottom — Orphan Records table**: Files that couldn't be found anywhere on disk

---

**Scan Controls (top of the repair section):**

| Control | What it does |
|---|---|
| **Mode: Deep Scan (Smart)** | The scanner automatically figures out the most likely folders to search — it looks at where your broken records last lived, walks up the folder tree to find what still exists, then expands from there. Also checks all non-C drives. |
| **Mode: Target Folder / Drive** | You pick a specific folder or drive root to scan. A **Browse...** button appears to let you choose. Best when you know exactly where the files moved to. |
| **Match: Filename + Hash (Recommended)** | Matches files first by filename, then **verifies the match by computing an MD5 hash**. The safest option. |
| **Match: Filename Only (Fast)** | Matches by filename alone — no hash check. Very fast, but may produce false matches if two different files share a name. |
| **Match: Hash Only (Thorough)** | Computes a full MD5 of every file it encounters. Finds files even if they were renamed. Slow on large drives. |
| **Start Scan** (blue button) | Begins the scan with the selected settings. A slim progress bar appears during the scan. |
| **Stop** (red button) | Cancels the scan mid-way. Only visible while a scan is running. |

---

**Relocated Files** (top-right table):

After a scan, this table lists every missing file that was found at a new location.

| Column | Contents |
|---|---|
| **File Name** | The original filename |
| **Old Path** | Where the database expects the file to be |
| **New Path** | Where the scan actually found it |
| **Match** | How the file was identified: `Filename`, `Hash`, or `Hash+Filename` (green = verified by hash, orange = filename only) |

Below the table:

| Control | What it does |
|---|---|
| **Fix mode: Update Database** | Keeps the file where it currently is and updates `library.db` to point to the new location. No files are moved. |
| **Fix mode: Move File Back** | Physically moves each found file back to the path the database expects. Creates any missing folders needed. |
| **Apply All Fixes** (green button) | Applies the chosen fix mode to every row in the Relocated Files table. Only enabled after a scan finds results. |

---

**Orphan Records** (bottom-right table):

Files listed here were found to be missing from disk and **could not be located anywhere** during the scan. They are "dead" database entries with no matching file.

| Column | Contents |
|---|---|
| <img src="assets/uisvg/check.svg" width="16" height="16"> checkbox | Check the rows you want to delete |
| **File Name** | The filename recorded in the database |
| **Last Known Path** | The path the database last had for this file |

| Control | What it does |
|---|---|
| **Select All** | Checks all orphan rows at once |
| **Delete Selected Orphans** (dark red button) | Permanently removes the checked records from `library.db` (Images, ImageTags, and tagless tables). Requires confirmation. **A timestamped backup of `library.db` is automatically created first.** |
| **Recall Backup** (yellow button) | Restores `library.db` from the backup created just before the last deletion. Only visible after a deletion has been performed in the current session. |

---

### Interface Tab

Controls the visual and performance settings of the app.

| Setting | Options | Description |
|---|---|---|
| **Window UI Scale** | 50%, 70%, 90%, 100%, 125%, 150%, 175%, 200%, Custom... | Scales the entire UI. Takes effect after restarting the app. You can also type a custom percentage. |
| **Performance Mode** | High Performance, Balanced (Default), Power Saver / Low End PC | Controls how many background thumbnail threads run. High = fastest thumbnails, Low = saves CPU and RAM on older machines. |

---

### Tag Manager Tab

A full-featured tag workstation for managing and tagging your media library. The tab has **three columns** side by side.

---

#### Column 1 — Inbox Queue

The left column is your main working queue. It shows untagged files waiting to be processed.

| Control | What it does |
|---|---|
| **Search bar** | Search your library by tag to find already-tagged files. Leave it empty to see the full untagged Inbox. Supports multi-tag search with commas. Has autocomplete. |
| **Import External Folder** (blue button) | Scans a folder you choose and adds any new media files it finds to the Inbox queue for tagging. Skips duplicates automatically. A progress bar appears during the scan. |
| **Find Matches in Cloud** (purple button) | Checks every file in your Inbox against a community tag database and downloads suggested tags for any matches it finds. |
| **Inbox grid** | Thumbnail grid of all files waiting to be tagged. Click any thumbnail to load it into the workspace. Files with pending changes are highlighted in green. |

---

#### Column 2 — Tags & Rename

The middle column shows and manages the tags for the currently selected file.

**File Rename section** (top):
- Type a new name in the rename field (without extension). An error indicator appears if a file with that name already exists in the same folder.
- The rename is applied when you click **Save All Pending Changes**.

**Active Tags section** (below rename):

| Control | What it does |
|---|---|
| **Filter active tags...** input | Instantly filter the tag list to find specific tags |
| **Tag list** | Shows all current tags for the selected file. Tags from the community cloud appear in purple with a <img src="assets/uisvg/cloud.svg" width="16" height="16"> icon. Check a tag's checkbox to mark it for deletion. Double-clicking a tag also deletes it. |
| **Add tag input** | Type a tag name and press Enter or click <img src="assets/uisvg/add.svg" width="16" height="16"> to add it. Has autocomplete from your full library tag list. Tags are normalized to lowercase with underscores. |
| **AI Tag** (purple button) | Runs an AI model against the current image and automatically suggests up to 31 tags. If the model files are not installed, a download dialog appears first with three model size options (Basic ~379MB / Balanced ~440MB / Advanced ~1.26GB). |
| **Delete Selected Active Tag** button | Removes all checked tags from the file after confirming. |

---

#### Column 3 — Media Workspace

The right column is a full media viewer and action center.

| Control | What it does |
|---|---|
| **Media preview area** | Shows the currently selected file. Supports images (auto-scaling), animated GIFs, and videos (with play/pause, skip ±10s, and a seekable progress bar that loops automatically). |
| **Console log** | A live black-and-green terminal-style log showing every import event, cloud sync result, AI tag result, and save operation with timestamps. |
| **Approve Selected / Batch Approve All** (green button) | When cloud-matched tags are pending, this button approves and saves them for all files at once without reviewing each one individually. |
| **Save All Pending Changes** (blue button) | Saves all tag additions, tag deletions, and file renames across all files you've modified — not just the current one. Files are moved from the Inbox into your permanent library and removed from the tagless queue. |

**Community Sharing** (bottom of tab):
- A checkbox: **"Help others by anonymously sharing these tags to the community cloud"** — when checked, your saved tags are added to an upload queue and contributed to the shared tag database in the background. Enabled by default.

---

### Image Dedup Tab

A tool for finding and removing duplicate images from your library using **perceptual image hashing (pHash)**.

**How the scan works:**
The scanner computes a 256-bit visual fingerprint for every image in your library. It then compares all fingerprints against each other. Images whose fingerprints are close enough (within the strictness setting) are grouped as duplicates. Groups are then sorted so the least-confident matches appear first for your review.

| Control | What it does |
|---|---|
| **Target tag input** | Optionally scope the scan to only images that have a specific tag (e.g., `creator:example_name`). Leave blank to scan your entire library. |
| **Scan Library** (blue button) | Starts the scan. A slim progress bar appears. The status label updates with the current phase: *Loading records → Calculating confidences → Clustering → Finalizing*. |
| **Auto-Delete Low Res** (red button) | After a scan, automatically sends the lower-resolution copy from each duplicate pair to the Recycle Bin. Requires confirmation. Only enabled once a scan has completed. |
| **Filter duplicates by tags...** input | Filters the list of displayed duplicate groups by tag name — useful when you have a large scan result. |
| **Strictness slider** | Range: **0 to 15**. Controls how visually similar images must be to count as duplicates.<br>• **0** = Exact pixel copies only<br>• **1–5** = Balanced — catches re-saves, compression artifacts, minor crops<br>• **6–15** = Loose — catches similar but not identical images (higher false-positive risk) |
| **Undo Last Action** (yellow button) | Restores the last file deleted. Also works with `Ctrl+Z`. Only visible after a deletion. |
| **Duplicate groups list** | Scrollable list of groups. Each group card shows thumbnail previews of the duplicate images side by side. |
| **Group Comparison panel** | When you click or keyboard-navigate to an image, it shows a full large-size side-by-side comparison of every image in that group. Each image shows its filename, resolution (e.g., `1920x1080`), and file size in MB beneath it. The clicked image is highlighted with a blue border. |

**Keyboard navigation** in the duplicate grid:
- Use **Arrow keys** to move focus between images within and across groups. The comparison panel updates automatically as focus moves.

**Per-image info shown in the scan results:**
- Filename, resolution, and file size for each duplicate
- Confidence score shown per group (lower confidence = less sure they are duplicates)

---

### Video Dedup Tab

A tool for finding duplicate or near-identical videos in your library, powered by the **VideoDuplicateFinder (VDF)** engine and **FFmpeg**.

> **First-time setup**: If the engine is not installed, a **Download VDF Engine** button (blue) will appear. Click it to automatically download and install both the VDF CLI and FFmpeg binaries (~150MB total). A progress bar and a live log show the download progress. Once installed, the button disappears.

**Layout — two panels side by side:**
- **Left panel**: Scrollable list of duplicate video groups found after a scan.
- **Right panel** (split vertically):
  - **Video Player** (top): Plays any video you click. Full controls included.
  - **Scan Log console** (bottom): Live output from the VDF engine during the scan.

| Control | What it does |
|---|---|
| **Visual Match Requirement slider** | Range: **80%–100%**. Sets how visually similar two videos must be to count as duplicates. **100%** = only exact frame-for-frame copies. Lower values find re-encodes, resizes, or slightly edited copies. |
| **Start Video Scan** (purple button) | Launches the VDF engine against your video library. The engine analyzes all video files found in your database, compares their visual fingerprints, and writes results. The progress bar and log update in real-time. |
| **Scan log console** | Shows live output from the scan engine including folder paths, percentage progress, and any warnings. |

**Each duplicate group card shows:**
- A **header** with the group number and video count
- **Video cards** side by side — each with:
  - A thumbnail captured from the middle of the video (loads in background)
  - Filename, resolution (frame size), file size, and duration
  - A **Recycle Bin** button — moves just that video to the Recycle Bin after confirmation. The file is also removed from your library database. When only one video remains in a group, the whole group card is automatically removed.
  - A **Select Exception** checkbox (appears when a group has 3+ videos) — check specific videos to exclude from the duplicate relationship
- A **Mark as 'Not Duplicates'** button (green, top-right of each group card) — permanently saves a rule so these videos are never flagged as duplicates again. If checkboxes are present, only the checked videos are exempted; otherwise the whole group is dismissed.

**Video Player (right panel):**

| Control | What it does |
|---|---|
| **Click any video card** | Starts playing that video in the player |
| **<img src="assets/Svg/back%2010Sec.svg" width="16" height="16"> Skip Back 10s** | Rewind 10 seconds |
| **<img src="assets/Svg/play.svg" width="16" height="16"> / <img src="assets/Svg/pause.svg" width="16" height="16"> Play/Pause** | Toggle playback |
| **<img src="assets/Svg/skip%2010Sec.svg" width="16" height="16"> Skip Forward 10s** | Fast-forward 10 seconds |
| **Progress slider** | Click or drag to seek to any position |
| **Time display** | Shows current position / total duration (HH:MM:SS or MM:SS) |

**Fast Resume**: If a previous scan's results exist, the tab automatically loads them when opened — no need to re-scan.

---

### Pagination Tab

A manga/comic **builder** tool. Use it to gather individual images from your library, arrange them in the right order, and save them as a named manga/comic collection — complete with tags — that then appears in the gallery and reader like any other manga folder.

The tab is divided into **three numbered columns**:

---

#### Column 1 — Search & Select

| Control | What it does |
|---|---|
| **Import Folder** (blue button) | Scans a folder on your computer and adds all image files inside (sorted by filename naturally) directly to the page list. If it detects subfolders (chapters), it imports them as a batch. |
| **Group / Ungroup** button | When batch-importing subfolders, this button appears at the top. Toggles the search grid between showing grouped folders or flattening all images into one view. |
| **Load Existing** (blue button) | Opens a picker window listing all your previously saved custom mangas along with their total page counts. Select one to load its pages, title, and tags so you can edit it. The create button changes to **Save Changes**. |
| **Clear / New** (red button) | Resets everything — clears the title, tags, page list, and search results to start fresh. |
| **Search by tag input** | Type a tag and press Enter to search your library. Results appear as image thumbnails. Has autocomplete. |
| **Search results grid** | Shows thumbnail previews of matching images. **Click to select** — selected images are immediately added to the page list on the right. Click again to deselect and remove them. Multiple selection is supported. |

---

#### Column 2 — Organize Pages

Shows the final ordered page list for your manga.

| Control | What it does |
|---|---|
| **Page list** | Displays all selected pages in order. Each item shows the filename and a **"Pg N"** page number label on the right edge. |
| **Drag & drop** | Drag any page up or down in the list to reorder pages. A blue drop indicator shows where the item will land. |
| **Move Up / Move Down** buttons | Move the currently selected page one position up or down. |
| **Right-Click (Double Spread)** | Right-click any page in the list and select **Attach to Next Page (Double Spread)**. This links the page to the next one so they display side-by-side as a single wide spread in the Manga Reader. A chain-link icon 🔗 appears visually connecting the two rows. |
| **Remove** button | Removes the selected page from the list (also deselects it in the search grid). |

---

#### Column 3 — Preview & Details

| Control | What it does |
|---|---|
| **Image preview** | Shows a scaled preview of whichever page is currently selected in either list. Updates with a short delay to avoid flicker. |
| **Manga/Comic Title** input | The name for your collection. Must be unique. Required before saving. |
| **Custom Tags** input | Comma-separated list of tags to attach to the manga (e.g., `creator_name, character`). Has autocomplete. |
| **Create Comic/Manga** button (purple) | Saves the manga to your library database with its pages in order, title, and tags. After saving, the first page image is used as the cover. If editing an existing manga, this button reads **Save Changes** instead. |

**After saving:**
- The manga appears in the gallery and can be opened in the Manga Reader.
- The app's tag autocomplete reloads to include any new tags.
- The form resets automatically, ready for the next collection.

---

**Bottom of Settings Dialog:**
| Button | Action |
|---|---|
| **Cancel** | Closes the dialog without saving |
| **Save Settings** | Saves all changes from the Database and Interface tabs |

---

## Supported Formats

| Type | Formats |
|---|---|
| **Images** | JPG, JPEG, PNG, GIF, BMP, WebP |
| **Videos** | MP4, MKV, AVI, MOV, WebM |
| **Manga / Manhwa** | Folders containing image files |

---

## 🎨 Visual Design

Media Nest uses a **VS Code–inspired dark theme** throughout the entire interface.

- **Background**: Deep dark (`#1e1e1e`) across all panels.
- **Sidebar & panels**: Slightly lighter dark (`#252526`) to create subtle visual separation.
- **Accent color**: Bright blue (`#007acc` / `#0e639c`) used on selected items, focused inputs, active buttons, and the loading bar.
- **Text**: Soft light grey (`#cccccc`) for readability without harsh contrast.
- **Font**: Segoe UI (Windows system font) for a native, clean look.
- **Dividers**: The draggable splitters between panels are thin dark bars that turn blue when hovered, giving clear visual feedback.
- **File tree items**: Highlight on hover and turn solid on selection with white text.
- **Gallery items**: Subtle border appears on hover; selected items get a deep blue highlight.
- **All icons**: SVG-based, so they stay crisp at any zoom level or DPI setting.
