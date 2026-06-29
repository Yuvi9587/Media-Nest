# Media Nest v3.0.0 Release Notes

This release introduces several new features focused on search improvements and database management. 

## What's New

### 1. Natural Language Smart Search
You can now search using plain English sentences by typing `Search: ` before your query.

* **Example:** `Search: makima wearing a suit in an office`
* **How it works:** The engine removes common filler words and categorizes the remaining terms. 
* **Character Anchors:** If it detects a character, series, or artist (like "Makima"), that tag becomes a strict requirement. General environment tags (like "suit" or "office") are treated as optional matches, giving you more flexible search results while ensuring the main subject is present.

### 2. Built-in Terminal
I added a built-in terminal for managing the SQLite database directly within the app, removing the need to use external database browsers.

* **Database Operations:** You can rename tags, merge tags, delete orphaned file records, or migrate file paths using commands.
* **Bulk Tagging:** Add a tag to multiple files by extension (e.g., `tag add "metadata:Video" --ext .mp4`).
* **Safety & Performance:** Destructive commands will prompt for confirmation. Long-running queries use a progress indicator to prevent the UI from freezing.
* **Searchable Output:** The terminal log supports standard `Ctrl+F` searching.

### 3. Manga Builder (Pagination Tab) Updates
The custom comic builder in the Pagination Tab has received a few quality-of-life updates.

* **Double-Page Spreads:** You can right-click any page in your list and select **Attach to Next Page (Double Spread)**. A chain-link icon will appear, and the reader will render those pages side-by-side.
* **Batch Folder Import:** The *Import Folder* button now detects subfolders (such as chapters) and imports them together as a batch.
* **Group / Ungroup View:** During batch imports, a toggle button is available to switch between viewing grouped folders or a flat list of images.

---

## Fixes & Improvements
- **Database Maintenance:** Fixed a bug where the "Delete Orphaned Files" button in the Database Repair tab would report success without actually removing the records.
- **Code Cleanup:** Removed unused internal comments across the Python backend to slightly reduce file size.
- **Search Optimization:** Added a new SQL index (`idx_imagetags_tag_id`) to the `ImageTags` table, which improves the speed of tag popularity lookups during Smart Searches.
