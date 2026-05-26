# Media-Nest

<img src="assets/Logo%201.png" width="250" align="right" alt="Media-Nest Logo" style="margin-top:-40px;">

Media-Nest is a high-performance desktop application designed for organizing, viewing, and managing extensive local image and video libraries. It focuses heavily on performance, leveraging multithreading and background processing to ensure the user interface remains responsive even when dealing with thousands of files. 

![Main Interface](assets/1.png)

## Core Features and Capabilities

The application offers a variety of advanced features to help you manage your media library efficiently. The user interface is designed with a premium, dark-themed aesthetic inspired by modern professional IDEs, minimizing eye strain during extended organizing sessions.

**Intelligent Media Organization**
Navigating through your media is streamlined by a smart tree navigation system that lets you effortlessly browse folders and galleries. 
*   **Multi-Tag Search**: A highly intelligent search bar allows you to quickly filter your entire library by combining inclusive and exclusive tags. For example, you can search for a specific character while explicitly excluding another.

**Advanced Duplicate Detection**
When it comes to managing duplicate content, Media-Nest offers robust tools to help you reclaim valuable storage space.
*   **Image Deduplication**: Utilizes perceptual hashing (pHash) algorithms to cluster and identify visually similar or exact duplicate images.
*   **Video Deduplication**: Integrates with a powerful backend CLI engine, utilizing FFmpeg and a specialized Video Duplicate Finder engine to scan your video library for exact matches.

![Media Viewer](assets/2.png)

**AI-Powered Auto-Tagging**
To drastically reduce the manual labor involved in organizing a large collection, Media-Nest includes an AI-powered auto-tagging system accessible through the tag manager.
*   **Hardware Acceleration**: Leverages the ONNX runtime, supporting CPU, NVIDIA CUDA, and DirectML execution providers to run efficiently on your specific hardware.
*   **Smart Predictions**: Analyzes images and video frames to automatically predict characters and apply tags, using a customizable fallback rule system based on visual traits like hair and eye color.

**High-Performance Viewers**
Media-Nest excels in media playback and viewing, providing specialized tools for different types of content.
*   **Video Player**: Features custom timeline controls, volume sliders, looping functionality, and a detached viewer mode that is perfect for multi-monitor setups.
*   **Comic Readers**: Provides specialized virtual readers capable of handling infinite vertical scrolling (ideal for manhwa) as well as classic paginated reading for manga.

## System Workflow and Usage

Managing your media library is a straightforward process designed to be seamless and non-blocking. A swarm of background worker threads handles resource-intensive tasks without freezing the main user interface.

*   **Initialization**: Point the application to your media library or load an existing SQLite database containing your tags and metadata.
*   **Background Processing**: The application asynchronously scans your directories, generating thumbnails and extracting video frames in the background.
*   **Navigation**: Use the sidebar search to find specific tags. The application will instantly query the database to update the main view with relevant files or galleries.
*   **Viewing**: Click an image to open it in the native viewer (double-click to zoom and pan), click a video to play it instantly, or open a folder of images to trigger the high-performance comic reader.

## Setup and Installation

The application requires Python 3.10 or higher. You will need to install the following dependencies: PyQt6, ONNX Runtime, OpenCV, Pillow, and ImageHash. 

**Installation Steps:**
1. Clone the repository to your local machine.
2. Install the required dependencies using pip. If you have an NVIDIA GPU, it is highly recommended to install `onnxruntime-gpu` instead of the standard package to speed up the AI auto-tagging process.
   ```bash
   pip install PyQt6 pillow imagehash onnxruntime opencv-python send2trash requests
   ```
3. Launch the application by running the main Python script.

**First-Time Configuration:**
*   Upon launching, you may be prompted to set your primary database folder. 
*   If you intend to use the video deduplication feature, navigate to that tab and use the provided button to download the required FFmpeg and CLI binaries.
*   You can adjust your custom UI scaling settings by modifying the configuration JSON file located in the root directory.

## Project Structure Overview

The architecture of the application is divided into logical components for easier maintenance and development.

*   **Main Entry Point**: Handles portable configuration, UI scaling, Windows taskbar integration, and launches the main application window.
*   **Application Logic (`Src/Logic/app.py`)**: Responsible for binding the user interface to the background workers. It manages the thumbnail generation swarm, handles database queries, and controls the media players.
*   **User Interface (`Src/Ui/interface.py`)**: Defines the layout, styling, and custom widgets, such as the smart scaling image viewer and custom video controls.
*   **Background Workers**: Modules like `Src/Logic/deduplication.py` and `Src/Logic/video_dedup.py` handle the heavy lifting for finding duplicate content.
*   **AI Engine (`Src/Logic/visual_sorter.py`)**: Loads ONNX models to analyze media frames and predict tags.
*   **Specialized Widgets (`Src/Ui/reader_widget.py`)**: Used specifically to render comic and manga pages smoothly.

## Usage Tips

*   **Multi-Monitor Setup**: Click the Detach Viewer button in the sidebar to pop the media player out into its own floating window.
*   **Zooming**: Double-clicking any static image will zoom in to its native resolution, allowing you to use the scrollbars or mouse wheel to navigate.
*   **Hardware Acceleration**: If the AI auto-tagger is running slowly, ensure you have the correct ONNX runtime installed and configured in your settings (CUDA for NVIDIA, DirectML for AMD/Intel).
