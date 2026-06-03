import os
import csv
import threading
import warnings
import re
import numpy as np
from PIL import Image

from PyQt6.QtCore import QSettings

warnings.filterwarnings("ignore", category=UserWarning, module="onnxruntime")

class VisualSorter:
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls, model_path, csv_path):
        if cls._instance is None:
            with cls._lock: 
                if cls._instance is None:
                    cls._instance = cls(model_path, csv_path)
        return cls._instance

    def __init__(self, model_path, csv_path):
        import onnxruntime as ort 
        
        settings = QSettings("MediaNest", "VisualSort")
        
        hw_choice = str(settings.value("execution_provider", "cpu"))
        
        providers = ["CPUExecutionProvider"]
        if hw_choice == "cuda":
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        elif hw_choice == "dml":
            providers = ["DmlExecutionProvider", "CPUExecutionProvider"]
            
        try:
            self.model = ort.InferenceSession(model_path, providers=providers)
            active_providers = self.model.get_providers()
            print("\n" + "="*40)
            print("🤖 VISUAL SORT ENGINE INITIALIZED")
            print("="*40)
            if "CUDAExecutionProvider" in active_providers:
                print("✅ Hardware Status : NVIDIA GPU (CUDA) Active!")
            elif "DmlExecutionProvider" in active_providers:
                print("✅ Hardware Status : AMD/Intel GPU (DirectML) Active!")
            else:
                print("⚠️ Hardware Status : CPU Mode Active (Standard/Fallback)")
            print(f"⚙️ Loaded Providers : {active_providers}")
            print("="*40 + "\n")
        except Exception as e:
            print(f"\n❌ Hardware Error: Failed to load '{hw_choice}'. Reason: {e}")
            print("⚠️ Falling back to safe CPU mode...\n")
            self.model = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        
        self.tags = []
        self.character_start_idx = None
        self.character_end_idx = None
        
        with open(csv_path, encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                tag_name = row[1].replace("_", " ").lower()
                category = row[2]
                if category == "4" and self.character_start_idx is None:
                    self.character_start_idx = reader.line_num - 2
                elif category != "4" and self.character_start_idx is not None and self.character_end_idx is None:
                    self.character_end_idx = reader.line_num - 2
                self.tags.append(tag_name)
                
        if self.character_end_idx is None:
            self.character_end_idx = len(self.tags)

    def process_image(self, image_path):
        try:
            def evaluate_single_frame(image_frame):
                input_layer = self.model.get_inputs()[0]
                target_size = input_layer.shape[1]
                ratio = float(target_size) / max(image_frame.size)
                new_size = tuple([int(x * ratio) for x in image_frame.size])
                image_resized = image_frame.resize(new_size, Image.LANCZOS)
                square = Image.new("RGB", (target_size, target_size), (255, 255, 255))
                square.paste(image_resized, ((target_size - new_size[0]) // 2, (target_size - new_size[1]) // 2))
                
                image_array = np.array(square).astype(np.float32)[:, :, ::-1]
                image_array = np.expand_dims(image_array, axis=0)
                
                preds = self.model.run(None, {input_layer.name: image_array})[0][0]
                
                char_preds = preds[self.character_start_idx:self.character_end_idx]
                char_tags = self.tags[self.character_start_idx:self.character_end_idx]
                
                general_preds = preds[:self.character_start_idx]
                general_tags = self.tags[:self.character_start_idx]
                
                current_threshold = 0.50
                
                top_general_indices = np.argsort(general_preds)[::-1][:20]
                top_tags_list = [(general_tags[i], float(general_preds[i])) for i in top_general_indices]

                result = {"best_char": None, "top_tags": top_tags_list}

                if len(char_tags) > 0:
                    global_top_indices = np.argsort(char_preds)[::-1][:3]
                    global_top_chars = [(char_tags[i].title(), float(char_preds[i])) for i in global_top_indices]
                    
                    global_max_score = global_top_chars[0][1] if global_top_chars else 0
                    if global_max_score > current_threshold:
                        result["best_char"] = global_top_chars[0][0]

                return result

            images_to_process = []
            video_extensions = ('.mp4', '.webm', '.mkv', '.avi', '.mov', '.m4v')
            
            if str(image_path).lower().endswith(video_extensions):
                import cv2
                cap = cv2.VideoCapture(image_path)
                if not cap.isOpened():
                    raise Exception("OpenCV failed to open video file.")
                    
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if total_frames > 0:
                    scan_points = [
                        (1, int(total_frames * 0.01)),
                        (5, int(total_frames * 0.05)),
                        (10, int(total_frames * 0.10)),
                        (15, int(total_frames * 0.15)),
                        (20, int(total_frames * 0.20)),
                        (30, int(total_frames * 0.30)),
                        (34, int(total_frames * 0.50)),
                        (38, int(total_frames * 0.50)),
                        (45, int(total_frames * 0.50)),
                        (50, int(total_frames * 0.50)),
                        (80, int(total_frames * 0.80)),
                        (90, int(total_frames * 0.90)),
                        (100, total_frames - 1)
                    ]
                    
                    for pct, mark in scan_points:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, mark)
                        ret, frame = cap.read()
                        if ret:
                            msec = cap.get(cv2.CAP_PROP_POS_MSEC)
                            seconds = int(msec / 1000)
                            mins = seconds // 60
                            rem_secs = seconds % 60
                            timestamp_str = f"{mins}:{rem_secs:02d}"
                            
                            frame_label = f"[Frame @ {pct}% | {timestamp_str}]"
                            
                            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            images_to_process.append((Image.fromarray(frame_rgb), frame_label))
                cap.release()
                
                if not images_to_process:
                    raise Exception("OpenCV failed to extract any frames.")
            else:
                image = Image.open(image_path)
                if getattr(image, "is_animated", False):
                    image.seek(image.n_frames // 2)
                    images_to_process.append((image.convert('RGB'), "[GIF Middle Frame]"))
                else:
                    images_to_process.append((image.convert('RGB'), "[Static Image]"))

            best_failure_result = None
            
            for idx, (img, frame_label) in enumerate(images_to_process):
                result = evaluate_single_frame(img)
                
                if result and result.get("best_char") is not None:
                    return result
                
                if result:
                    best_failure_result = result
                
            return best_failure_result

        except Exception as e:
            print(f"ONNX Evaluation Error: {e}")
            return None