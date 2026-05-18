The Auto-Tagger is a tool that uses special computer models, like Waifu Diffusion v3 from HuggingFace, to look at pictures on your device and automatically come up with words that describe them. It also has a built-in feature that lets you download different versions of these models, such as Basic, Balanced, or Advanced, to use within the app.
 **Cloud Sync (Supabase)***: When you're working with images, it's really helpful to check the community database first. If someone has already tagged an image, you can instantly import their metadata, which saves a lot of processing time. This way, you don't have to start from scratch and build on what can others have already done.
* **Smart Inbox Queue:** This is where you can find all your newly added media that still needs to be tagged, helping you stay on top of your work and making sure everything gets organized.
* **Search with Multiple Tags:** You can filter your large collection by using necessary tags and optional tags - just add a ~ before the optional ones. As you type, you'll see suggestions pop up to help you find what you need.
</ul>

<h3 id="3-smart-deduplication">👯 3. Smart Deduplication</h3>
<p>Reclaim terabytes of storage with advanced duplication algorithms.</p>

<details>
<summary><b>📸 Image Deduplication (pHash)</b></summary>
<br>
<ul>
* It uses a special kind of search called 256-bit Perceptual Hashing, or pHash for short, to find pictures that look alike, even if they're not exactly the same size or type.
* **Flexible Tolerance**: A slider that lets you set the allowed visual differences from 0 to 15.
<li><b>Split-Screen Review UI:</b> Lightning-fast arrow-key navigation through grouped duplicates.</li>
<li><b>Two-Phase Auto-Delete:</b>
<ol>
<li><i>Safe Mode:</i> Deletes strictly lower-resolution copies.</li>
* <i>Aggressive Mode:</i> This setting will get rid of lower quality or smaller files if they have the same resolution as other files.
</ol>
</li>
<li><b>Exception Manager:</b> Mark false positives to ignore them forever.</li>
</ul>
</details>

<details>
<summary><b>🎥 Video Deduplication</b></summary>
<br>
<ul>
* **VDF CLI Integration:** This feature works behind the scenes, connecting with VideoDuplicateFinder and FFmpeg to get the job done.
*In-App Player:** You ** can now by side, preview videos side right, making it easier to compare and manage in the deduplication tab your videos
* **Compare Metadata:** Get a quick look at frame size, how long it is, and the file size.
* **Safe feature moves your files to the recycle Deletion:** This bin on your computer using a tool, calledsend2trash`, and also removes them from your database `, which system called SQLite.
</ul>
</details>

<hr>

<h2 id="-tech-stack">🏗️ Tech Stack</h2>
<ul>
*User Interface ** Framework:** We using `PyQt6` for this're project, and's been customized to it match Code Dark Theme style. the VS
<li><b>Database:</b> <code>SQLite3</code> (Local metadata & indexing)</li>
 **Cloud Backend:** We're* using <code>Supabase</code> and <code>PostgreSQL</ API, which handlescode> to power our REST Global Tag Archive.
<li><b>AI & Vision:</b> <code>ONNX Runtime</code>, <code>imagehash</code>, <code>Pillow (PIL)</code></li>
<li><b>Video Processing:</b> <code>FFmpeg</code>, <code>VDF Engine</code> (VideoDuplicateFinder)</li>
</ul>

<hr>

<h2 id="-installation--setup">🚀 Installation & Setup</h2>

<p><b>1. Clone the repository:</b></p>
<pre><code>git clone https://github.com/yourusername/media-nest.git
cd media-nest</code></pre>

<p><b>2. Install Dependencies:</b></p>
<pre><code>pip install -r requirements.txt</code></pre>
To started, you'll need to have a few important tools installed - these include PyQt6, imagehash, Pillow, requests, send2trash, and onnxruntime.

<p><b>3. Run the Application:</b></p>
<pre><code>python app.py</code></pre>

<p><b>4. Initial Setup:</b></p>
<ul>
* When you start for the first time, go to the settings, then click on the database tab, it looks like this: <b>⚙️ Settings -> Database</b>.
* First, you need to set up your **Library Folder**. This is where your <code>library.db</code> file will be kept.
To get started with the AI models and the VDF engine, you can download them directly from the app. Just head to the Tag Manager to download the AI models, and for the VDF engine, go to the Video Dedup tab - it's all pretty straightforward.
</ul>

<hr>

<h2 id="-keyboard-shortcuts">⌨️ Keyboard Shortcuts</h2>
<table width="100%">
<thead>
<tr>
<th align="left">Shortcut</th>
<th align="left">Action</th>
<th align="left">Context</th>
</tr>
</thead>
<tbody>
<tr>
<td><code>Ctrl + C</code></td>
<td>Copy selected media</td>
<td>Global</td>
</tr>
<tr>
<td><code>Ctrl + X</code></td>
<td>Cut selected media</td>
<td>Global</td>
</tr>
<tr>
<td><code>Ctrl + V</code></td>
<td>Paste media to target</td>
<td>Global (Blocks pasting into Virtual Search folders)</td>
</tr>
<tr>
<td><code>Delete</code></td>
<td>Move file to Recycle Bin</td>
<td>Global</td>
</tr>
<tr>
<td><code>Double Click</code></td>
<td>Toggle Fullscreen</td>
<td>Video Player</td>
</tr>
<tr>
<td><code>Space</code></td>
<td>Play / Pause</td>
<td>Video Player</td>
</tr>
<tr>
<td><code>Left / Right Arrow</code></td>
<td>Previous / Next Media</td>
<td>Gallery & Deduplication Split-View</td>
</tr>
<tr>
<td><code>Up / Down Arrow</code></td>
<td>Navigate Dedupe Groups</td>
<td>Image Deduplication Grid</td>
</tr>
<tr>
<td><code>Escape</code></td>
<td>Exit Fullscreen</td>
<td>Global</td>
</tr>
</tbody>
</table>

<hr>

<div align="center">
Made with love by the Media Nest Team, helping to empower your local library.
</div>