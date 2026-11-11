import json
import os
import sys
import time
import tempfile
import threading
from typing import Dict, Any, Callable, Optional
import copy


from app.db.db_interface import DBInterface

class CrossProcessLock:
    """Safe cross-process file lock using operating system kernel primitives."""
    def __init__(self, lock_path: str):
        import hashlib
        lock_name = hashlib.md5(os.path.abspath(lock_path).encode("utf-8")).hexdigest()
        self.lock_file = os.path.join(tempfile.gettempdir(), f"tw_lock_{lock_name}.lck")
        self._fd = None
    
    def __enter__(self):
        self._fd = open(self.lock_file, "a+")
        if sys.platform == "win32":
            import msvcrt
            while True:
                try:
                    self._fd.seek(0)
                    msvcrt.locking(self._fd.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except (BlockingIOError, OSError):
                    time.sleep(0.05)
        else:
            import fcntl
            fcntl.flock(self._fd.fileno(), fcntl.LOCK_EX)
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._fd is not None:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    self._fd.seek(0)
                    msvcrt.locking(self._fd.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            finally:
                self._fd.close()
                self._fd = None

class JsonDB(DBInterface):
    """File-based persistence using atomic writes and cross-worker directory locks."""
    def read(self, collection_path: str) -> Any:
        if not os.path.exists(collection_path):
            return None
        
        # We don't strictly need a lock for reading because writes are atomic via os.replace.
        # But we do need read retries in case os.replace happens exactly during open().
        retries = 3
        for i in range(retries):
            try:
                with open(collection_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                if i == retries - 1:
                    raise RuntimeError(f"Failed to read {collection_path}: {str(e)}")
                time.sleep(0.05)

    def write(self, collection_path: str, data: Any) -> None:
        with CrossProcessLock(collection_path):
            self._atomic_write(collection_path, data)

    def update(self, collection_path: str, update_fn: Callable[[Any], Any]) -> Any:
        with CrossProcessLock(collection_path):
            data = None
            if os.path.exists(collection_path):
                with open(collection_path, "r", encoding="utf-8") as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        data = []
            
            # Apply business logic
            updated_data = update_fn(data)
            
            # Retry system for writing with exponential backoff
            retries = 3
            for i in range(retries):
                try:
                    self._atomic_write(collection_path, updated_data)
                    break
                except Exception as e:
                    if i == retries - 1:
                        raise e
                    time.sleep(0.1 * (2 ** i)) # Exponential backoff
                    
            return updated_data

    def _atomic_write(self, file_path: str, data: Any) -> None:
        import shutil
        dir_name = os.path.dirname(file_path) or "."
        
        # Maintain .backup.json for Crash-Safe Recovery
        if os.path.exists(file_path):
            backup_path = f"{file_path}.backup.json"
            try:
                shutil.copy2(file_path, backup_path)
            except Exception:
                pass
                
        fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix="tmp_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, file_path)
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e

def recover_db_files(db_directory: str):
    import shutil
    import glob
    from app.core.logger import app_logger
    
    if not os.path.exists(db_directory):
        return
        
    for json_file in glob.glob(os.path.join(db_directory, "*.json")):
        if json_file.endswith(".backup.json"):
            continue
            
        is_corrupt = False
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                json.load(f)
        except (json.JSONDecodeError, OSError):
            is_corrupt = True
            
        if is_corrupt:
            backup_path = f"{json_file}.backup.json"
            if os.path.exists(backup_path):
                try:
                    shutil.copy2(backup_path, json_file)
                    app_logger.info(
                        f"Database Recovery: Corrupted JSON detected. Auto-restored {os.path.basename(json_file)} from backup.",
                        extra={"request_id": "SYSTEM_BOOT", "endpoint": "STARTUP", "status_code": 0, "response_time_ms": 0, "method": "SYS"}
                    )
                except Exception as e:
                    app_logger.error(f"Failed to recover {json_file}: {str(e)}", extra={"request_id": "SYSTEM_BOOT", "endpoint": "STARTUP", "status_code": 500, "response_time_ms": 0, "method": "SYS"})
            else:
                app_logger.error(f"Database Recovery Failed: {json_file} is corrupt and no backup exists.", extra={"request_id": "SYSTEM_BOOT", "endpoint": "STARTUP", "status_code": 500, "response_time_ms": 0, "method": "SYS"})

class MemoryCache(DBInterface):
    """Proxy layer to cache reads for 3 seconds and pass writes down."""
    def __init__(self, backend: DBInterface):
        self.backend = backend
        self._cache = {}
        self._cache_lock = threading.Lock()
        self.CACHE_TTL = 3.0 # seconds

    def read(self, collection_path: str) -> Any:
        with self._cache_lock:
            cached = self._cache.get(collection_path)
            if cached and (time.time() - cached['time'] < self.CACHE_TTL):
                return copy.deepcopy(cached['data'])
                
        # Cache miss or expired
        data = self.backend.read(collection_path)
        
        with self._cache_lock:
            self._cache[collection_path] = {
                'time': time.time(),
                'data': copy.deepcopy(data)
            }
        return data

    def write(self, collection_path: str, data: Any) -> None:
        self.backend.write(collection_path, data)
        self._invalidate(collection_path)

    def update(self, collection_path: str, update_fn: Callable[[Any], Any]) -> Any:
        updated_data = self.backend.update(collection_path, update_fn)
        self._invalidate(collection_path)
        return updated_data

    def _invalidate(self, collection_path: str):
        with self._cache_lock:
            if collection_path in self._cache:
                del self._cache[collection_path]

# Singleton instance of the storage stack
db_instance = MemoryCache(JsonDB())

def read_json(file_path: str) -> Any:
    return db_instance.read(file_path)

def write_json(file_path: str, data: Any) -> None:
    db_instance.write(file_path, data)

def update_json(file_path: str, update_fn: Callable[[Any], Any]) -> Any:
    return db_instance.update(file_path, update_fn)
