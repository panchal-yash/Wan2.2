# Copyright 2024 Sequential Queue Manager for Wan S2V Processing
import json
import queue
import threading
import time
import logging
import os
import shutil
import subprocess
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Dict, Optional, Any
from pathlib import Path

# Import R2Client - this will be resolved at runtime
import sys
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class RequestStatus(Enum):
    """Request processing status"""
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"
    FAILED_DOWNLOAD = "failed_download"
    FAILED_PROCESSING = "failed_processing"
    FAILED_UPLOAD = "failed_upload"


@dataclass
class ProcessingRequest:
    """Data class for processing requests"""
    user_id: str
    request_id: str
    prompt: str
    image_r2_path: str
    audio_r2_path: str
    size: str = "832*480"
    sample_guide_scale: float = 4.0
    sample_steps: int = 20
    output_bucket: Optional[str] = None
    ckpt_dir: str = "./Wan2.2-S2V-14B/"
    
    # Processing metadata
    status: RequestStatus = RequestStatus.QUEUED
    message: str = "Request queued for processing"
    progress: int = 0
    queue_position: int = 0
    created_time: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    local_workspace: Optional[str] = None
    local_output_file: Optional[str] = None
    r2_output_path: Optional[str] = None
    public_url: Optional[str] = None
    error_details: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = asdict(self)
        # Convert enum to string
        if isinstance(result['status'], RequestStatus):
            result['status'] = result['status'].value
        return result


class WorkspaceManager:
    """Manages local workspace for processing requests"""
    
    def __init__(self, base_workspace_dir: str = "workspace"):
        self.base_workspace_dir = Path(base_workspace_dir)
        self.base_workspace_dir.mkdir(exist_ok=True)
        
    def create_workspace(self, user_id: str, request_id: str) -> str:
        """Create workspace directory for a request"""
        workspace_path = self.base_workspace_dir / user_id / request_id
        workspace_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Created workspace: {workspace_path}")
        return str(workspace_path)
    
    def cleanup_workspace(self, workspace_path: str) -> bool:
        """Clean up workspace directory"""
        try:
            if os.path.exists(workspace_path):
                shutil.rmtree(workspace_path)
                logger.info(f"Cleaned up workspace: {workspace_path}")
                return True
            return True
        except Exception as e:
            logger.error(f"Failed to cleanup workspace {workspace_path}: {str(e)}")
            return False
    
    def get_local_paths(self, workspace_path: str) -> Dict[str, str]:
        """Get standard local file paths for a workspace"""
        workspace = Path(workspace_path)
        return {
            'image': str(workspace / "image.jpg"),
            'audio': str(workspace / "audio.wav"),
            'output': str(workspace / "output.mp4")
        }


class SequentialQueueManager:
    """Manages sequential processing queue for S2V requests"""
    
    def __init__(self, r2_client: Any, 
                 workspace_manager: WorkspaceManager,
                 output_bucket: str = "output-bucket",
                 cleanup_after_processing: bool = True):
        self.r2_client = r2_client
        self.workspace_manager = workspace_manager
        self.output_bucket = output_bucket
        self.cleanup_after_processing = cleanup_after_processing
        
        # Queue management
        self.processing_queue = queue.Queue()
        self.request_status: Dict[str, ProcessingRequest] = {}
        self.status_lock = threading.Lock()
        self.current_processing: Optional[ProcessingRequest] = None
        
        # Worker thread
        self.worker_thread = None
        self.is_running = False
        
        logger.info("Sequential queue manager initialized")
    
    def start_worker(self):
        """Start the background worker thread"""
        if self.worker_thread and self.worker_thread.is_alive():
            logger.warning("Worker thread already running")
            return
        
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        logger.info("Worker thread started")
    
    def stop_worker(self):
        """Stop the background worker thread"""
        self.is_running = False
        if self.worker_thread and self.worker_thread.is_alive():
            # Add a sentinel to wake up the worker
            self.processing_queue.put(None)
            self.worker_thread.join(timeout=5)
        logger.info("Worker thread stopped")
    
    def add_request(self, request: ProcessingRequest) -> bool:
        """Add a new request to the processing queue"""
        request_key = f"{request.user_id}_{request.request_id}"
        
        with self.status_lock:
            if request_key in self.request_status:
                logger.warning(f"Request {request_key} already exists")
                return False
            
            # Set initial metadata
            request.created_time = datetime.now().isoformat()
            request.status = RequestStatus.QUEUED
            request.queue_position = self.processing_queue.qsize() + 1
            
            # Store in status tracker
            self.request_status[request_key] = request
        
        # Add to processing queue
        self.processing_queue.put(request)
        
        logger.info(f"Added request {request_key} to queue (position: {request.queue_position})")
        return True
    
    def get_request_status(self, user_id: str, request_id: str) -> Optional[ProcessingRequest]:
        """Get status of a specific request"""
        request_key = f"{user_id}_{request_id}"
        with self.status_lock:
            return self.request_status.get(request_key)
    
    def get_queue_info(self) -> Dict[str, Any]:
        """Get current queue information"""
        with self.status_lock:
            queue_size = self.processing_queue.qsize()
            current = self.current_processing.to_dict() if self.current_processing else None
            
            # Get queue positions
            queued_requests = []
            for req_key, req in self.request_status.items():
                if req.status == RequestStatus.QUEUED:
                    queued_requests.append({
                        'user_id': req.user_id,
                        'request_id': req.request_id,
                        'queue_position': req.queue_position,
                        'created_time': req.created_time
                    })
            
            return {
                'queue_size': queue_size,
                'current_processing': current,
                'queued_requests': sorted(queued_requests, key=lambda x: x['queue_position']),
                'worker_running': self.is_running
            }
    
    def _worker_loop(self):
        """Main worker loop - processes requests sequentially"""
        logger.info("Worker loop started")
        
        while self.is_running:
            try:
                # Get next request (blocks until available)
                request = self.processing_queue.get(timeout=1.0)
                
                # Check for sentinel (stop signal)
                if request is None:
                    break
                
                # Process the request
                self._process_single_request(request)
                
                # Mark task as done
                self.processing_queue.task_done()
                
            except queue.Empty:
                # Timeout - continue loop to check is_running
                continue
            except Exception as e:
                logger.error(f"Error in worker loop: {str(e)}")
                # Continue processing other requests
                continue
        
        logger.info("Worker loop finished")
    
    def _process_single_request(self, request: ProcessingRequest):
        """Process a single request through the complete pipeline"""
        request_key = f"{request.user_id}_{request.request_id}"
        
        try:
            with self.status_lock:
                self.current_processing = request
                request.start_time = datetime.now().isoformat()
            
            logger.info(f"Starting processing for {request_key}")
            
            # Step 1: Download assets from R2
            if not self._download_assets(request):
                self._mark_failed(request, RequestStatus.FAILED_DOWNLOAD)
                return
            
            # Step 2: Execute video generation
            if not self._execute_generation(request):
                self._mark_failed(request, RequestStatus.FAILED_PROCESSING)
                return
            
            # Step 3: Upload result to R2
            if not self._upload_result(request):
                self._mark_failed(request, RequestStatus.FAILED_UPLOAD)
                return
            
            # Step 4: Mark as completed
            self._mark_completed(request)
            
        except Exception as e:
            logger.error(f"Unexpected error processing {request_key}: {str(e)}")
            self._mark_failed(request, RequestStatus.FAILED, str(e))
        
        finally:
            # Cleanup and reset current processing
            if request.local_workspace and self.cleanup_after_processing:
                self.workspace_manager.cleanup_workspace(request.local_workspace)
            
            with self.status_lock:
                self.current_processing = None
    
    def _download_assets(self, request: ProcessingRequest) -> bool:
        """Download image and audio assets from R2"""
        self._update_status(request, RequestStatus.DOWNLOADING, "Downloading assets from R2...", 10)
        
        try:
            # Create workspace
            request.local_workspace = self.workspace_manager.create_workspace(
                request.user_id, request.request_id
            )
            
            # Get local file paths
            local_paths = self.workspace_manager.get_local_paths(request.local_workspace)
            
            # Download image
            self._update_status(request, RequestStatus.DOWNLOADING, "Downloading image...", 15)
            if not self.r2_client.download_file(request.image_r2_path, local_paths['image']):
                request.error_details = f"Failed to download image: {request.image_r2_path}"
                return False
            
            # Download audio
            self._update_status(request, RequestStatus.DOWNLOADING, "Downloading audio...", 25)
            if not self.r2_client.download_file(request.audio_r2_path, local_paths['audio']):
                request.error_details = f"Failed to download audio: {request.audio_r2_path}"
                return False
            
            logger.info(f"Successfully downloaded assets for {request.user_id}/{request.request_id}")
            return True
            
        except Exception as e:
            request.error_details = f"Error downloading assets: {str(e)}"
            logger.error(request.error_details)
            return False
    
    def _execute_generation(self, request: ProcessingRequest) -> bool:
        """Execute the video generation using generate.py"""
        self._update_status(request, RequestStatus.PROCESSING, "Generating video...", 30)
        
        try:
            # Get local file paths
            if not request.local_workspace:
                request.error_details = "No workspace available"
                return False
                
            local_paths = self.workspace_manager.get_local_paths(request.local_workspace)
            
            # Build command arguments
            cmd = [
                "python", "generate.py",
                "--task", "s2v-14B",
                "--size", request.size,
                "--ckpt_dir", request.ckpt_dir,
                "--offload_model", "False",
                "--convert_model_dtype",
                "--prompt", request.prompt,
                "--image", local_paths['image'],
                "--audio", local_paths['audio'],
                "--sample_guide_scale", str(request.sample_guide_scale),
                "--sample_steps", str(request.sample_steps),
                "--save_file", local_paths['output']
            ]
            
            logger.info(f"Executing generation command for {request.user_id}/{request.request_id}")
            logger.debug(f"Command: {' '.join(cmd)}")
            
            # Execute the command
            self._update_status(request, RequestStatus.PROCESSING, "Running video generation...", 50)
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=os.getcwd(),  # Run from the project root
                timeout=1800  # 30 minute timeout
            )
            
            if result.returncode != 0:
                request.error_details = f"Generation failed: {result.stderr}"
                logger.error(request.error_details)
                return False
            
            # Verify output file exists
            if not os.path.exists(local_paths['output']):
                request.error_details = "Generation completed but output file not found"
                logger.error(request.error_details)
                return False
            
            request.local_output_file = local_paths['output']
            self._update_status(request, RequestStatus.PROCESSING, "Video generation completed", 80)
            
            logger.info(f"Successfully generated video for {request.user_id}/{request.request_id}")
            return True
            
        except subprocess.TimeoutExpired:
            request.error_details = "Generation timed out after 30 minutes"
            logger.error(request.error_details)
            return False
        except Exception as e:
            request.error_details = f"Error executing generation: {str(e)}"
            logger.error(request.error_details)
            return False
    
    def _upload_result(self, request: ProcessingRequest) -> bool:
        """Upload generated video to R2"""
        self._update_status(request, RequestStatus.UPLOADING, "Uploading result to R2...", 85)
        
        try:
            if not request.local_output_file or not os.path.exists(request.local_output_file):
                request.error_details = "No local output file to upload"
                return False
            
            # Generate R2 output path
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_bucket = request.output_bucket or self.output_bucket
            request.r2_output_path = f"{output_bucket}/videos/{request.user_id}/{request.request_id}_{timestamp}.mp4"
            
            # Upload to R2
            if not self.r2_client.upload_file(request.local_output_file, request.r2_output_path):
                request.error_details = f"Failed to upload to R2: {request.r2_output_path}"
                return False
            
            # Generate public URL if available
            request.public_url = self.r2_client.generate_public_url(request.r2_output_path)
            
            self._update_status(request, RequestStatus.UPLOADING, "Upload completed", 95)
            
            logger.info(f"Successfully uploaded result for {request.user_id}/{request.request_id}")
            return True
            
        except Exception as e:
            request.error_details = f"Error uploading result: {str(e)}"
            logger.error(request.error_details)
            return False
    
    def _update_status(self, request: ProcessingRequest, status: RequestStatus, 
                      message: str, progress: int):
        """Update request status"""
        with self.status_lock:
            request.status = status
            request.message = message
            request.progress = progress
            
            # Update queue positions for queued requests
            if status != RequestStatus.QUEUED:
                for other_req in self.request_status.values():
                    if (other_req.status == RequestStatus.QUEUED and 
                        other_req.queue_position > request.queue_position):
                        other_req.queue_position -= 1
    
    def _mark_completed(self, request: ProcessingRequest):
        """Mark request as completed"""
        with self.status_lock:
            request.status = RequestStatus.COMPLETED
            request.message = "Video generation completed successfully"
            request.progress = 100
            request.end_time = datetime.now().isoformat()
        
        logger.info(f"Request {request.user_id}/{request.request_id} completed successfully")
    
    def _mark_failed(self, request: ProcessingRequest, status: RequestStatus, 
                    error_details: Optional[str] = None):
        """Mark request as failed"""
        with self.status_lock:
            request.status = status
            request.message = f"Processing failed: {status.value}"
            request.progress = 0
            request.end_time = datetime.now().isoformat()
            if error_details:
                request.error_details = error_details
        
        logger.error(f"Request {request.user_id}/{request.request_id} failed: {status.value}")