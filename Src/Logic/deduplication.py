import os
import sqlite3
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
import imagehash
from PyQt6.QtCore import QThread, pyqtSignal
from collections import defaultdict

class DeduplicationWorker(QThread):
    progress_signal = pyqtSignal(int, int)  
    status_signal = pyqtSignal(str)         
    duplicates_found = pyqtSignal(list)     
    finished_signal = pyqtSignal()

    def __init__(self, db_path, threshold, target_tag=None):
        super().__init__()
        self.db_path = db_path
        self.is_running = True
        self.threshold = threshold
        self.target_tag = target_tag

    def run(self):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.cursor()

            try:
                cursor.execute("ALTER TABLE Images ADD COLUMN phash TEXT")
            except sqlite3.OperationalError:
                pass 
            
            cursor.execute("CREATE TABLE IF NOT EXISTS IgnoredPairs (hash1 TEXT, hash2 TEXT, PRIMARY KEY (hash1, hash2))")
            conn.commit()

            self.status_signal.emit("Loading exclusion rules...")
            cursor.execute("SELECT hash1, hash2 FROM IgnoredPairs")
            ignored_pairs = {tuple(sorted((h1, h2))) for h1, h2 in cursor.fetchall()}

            self.status_signal.emit("Fetching database records...")
            
            if self.target_tag:
                cursor.execute("""
                    SELECT DISTINCT i.hash, i.file_path, i.phash 
                    FROM Images i
                    JOIN ImageTags it ON i.hash = it.hash
                    JOIN Tags t ON it.tag_id = t.tag_id
                    WHERE t.tag_name LIKE ?
                """, (f"%{self.target_tag}%",))
                rows = cursor.fetchall()
            else:
                cursor.execute("SELECT hash, file_path, phash FROM Images")
                rows = cursor.fetchall()
                try:
                    cursor.execute("SELECT hash, file_path, phash FROM tagless")
                    rows.extend(cursor.fetchall())
                except sqlite3.OperationalError:
                    pass
            
            valid_images = []
            images_updated = 0
            
            for i, row in enumerate(rows):
                if not self.is_running: break
                md5_hash, file_path, current_phash = row
                
                if i % 10 == 0:
                    self.progress_signal.emit(i, len(rows))

                if not os.path.exists(file_path): continue

                valid_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
                if os.path.splitext(file_path)[1].lower() not in valid_exts: continue

                if not current_phash or len(current_phash) < 64:
                    self.status_signal.emit(f"Upgrading to 256-bit pHash: {os.path.basename(file_path)}")
                    try:
                        img = Image.open(file_path)
                        current_phash = str(imagehash.phash(img, hash_size=16))
                        cursor.execute("UPDATE Images SET phash = ? WHERE hash = ?", (current_phash, md5_hash))
                        try:
                            cursor.execute("UPDATE tagless SET phash = ? WHERE hash = ?", (current_phash, md5_hash))
                        except sqlite3.OperationalError:
                            pass
                        
                        images_updated += 1
                        if images_updated % 100 == 0:
                            conn.commit()
                    except Exception:
                        continue

                if current_phash:
                    valid_images.append({
                        'hash': md5_hash,
                        'path': file_path,
                        'phash_int': int(current_phash, 16) 
                    })
            
            if images_updated > 0:
                conn.commit()

            self.status_signal.emit("Calculating match confidences...")
            total_imgs = len(valid_images)
            edges = []

            for i in range(total_imgs):
                if not self.is_running: break
                if i % 50 == 0: self.progress_signal.emit(i, total_imgs)
                
                img1 = valid_images[i]
                for j in range(i + 1, total_imgs):
                    img2 = valid_images[j]
                    
                    dist = (img1['phash_int'] ^ img2['phash_int']).bit_count()
                    
                    if dist <= self.threshold:
                        pair = tuple(sorted((img1['hash'], img2['hash'])))
                        if pair not in ignored_pairs:
                            confidence = 100.0 - ((dist / 256.0) * 100.0)
                            edges.append((i, j, confidence))

            self.status_signal.emit("Clustering duplicates...")
            graph = defaultdict(list)
            edge_weights = {}
            for u, v, conf in edges:
                graph[u].append(v)
                graph[v].append(u)
                edge_weights[tuple(sorted((u, v)))] = conf

            visited = set()
            clusters = []

            for i in range(total_imgs):
                if i not in visited and i in graph:
                    cluster_nodes = []
                    stack = [i]
                    while stack:
                        node = stack.pop()
                        if node not in visited:
                            visited.add(node)
                            cluster_nodes.append(node)
                            stack.extend(graph[node])
                    if len(cluster_nodes) > 1:
                        clusters.append(cluster_nodes)

            self.status_signal.emit("Finalizing results...")
            duplicate_lists = []
            
            for cluster in clusters:
                group_data = []
                hashes_for_query = []
                
                for node_idx in cluster:
                    img = valid_images[node_idx]
                    group_data.append({'path': img['path'], 'hash': img['hash']})
                    hashes_for_query.append(img['hash'])
                
                cluster_confidences = []
                for idx_a in range(len(cluster)):
                    for idx_b in range(idx_a + 1, len(cluster)):
                        pair = tuple(sorted((cluster[idx_a], cluster[idx_b])))
                        if pair in edge_weights:
                            cluster_confidences.append(edge_weights[pair])
                
                avg_confidence = sum(cluster_confidences) / len(cluster_confidences) if cluster_confidences else 100.0
                
                placeholders = ','.join(['?'] * len(hashes_for_query))
                cursor.execute(f'''
                    SELECT DISTINCT t.tag_name 
                    FROM Tags t 
                    JOIN ImageTags it ON t.tag_id = it.tag_id 
                    WHERE it.hash IN ({placeholders})
                ''', hashes_for_query)
                
                tags = [row[0] for row in cursor.fetchall()]
                tags_string = " ".join(tags).lower()
                
                duplicate_lists.append((group_data, tags_string, round(avg_confidence, 2)))

            duplicate_lists.sort(key=lambda x: x[2])
            self.duplicates_found.emit(duplicate_lists)
            conn.close()

        except Exception as e:
            self.status_signal.emit(f"Error: {e}")
        finally:
            self.finished_signal.emit()

    def stop(self):
        self.is_running = False
        self.wait()