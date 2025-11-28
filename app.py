#!/usr/bin/env python3
"""
Wan S2V Flask API Server with R2 Integration and Sequential Processing

This Flask API server accepts S2V generation requests from backend servers,
downloads assets from Cloudflare R2, processes them sequentially through the
Wan model, and uploads results back to R2.

Features:
- Sequential processing queue (no parallel GPU usage)
- R2 integration for input/output assets
- Real-time status tracking
- Robust error handling
- Clean workspace management
"""

import os
import logging
import argparse
import signal
import sys
from datetime import datetime
from typing import Dict, Any, Optional

from flask import Flask, request, jsonify, abort
from flask_cors import CORS
from dotenv import load_dotenv

# Import our custom modules
from r2_client import R2Client, create_r2_client_from_env
from queue_manager import SequentialQueueManager, WorkspaceManager, ProcessingRequest, RequestStatus

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(name)s - %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('wan_api.log')
    ]
)

logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
CORS(app)

# Global variables for queue manager and clients
queue_manager: Optional[SequentialQueueManager] = None
r2_client: Optional[R2Client] = None


def initialize_services():
    """Initialize R2 client and queue manager"""
    global queue_manager, r2_client
    
    try:
        # Initialize R2 client
        logger.info("Initializing R2 client...")
        r2_client = create_r2_client_from_env()
        
        # Initialize workspace manager
        workspace_manager = WorkspaceManager(
            base_workspace_dir=os.getenv('WORKSPACE_DIR', 'workspace')
        )
        
        # Initialize queue manager
        logger.info("Initializing queue manager...")
        cleanup_after_processing = os.getenv('CLEANUP_WORKSPACE', 'true').lower() == 'true'
        
        queue_manager = SequentialQueueManager(
            r2_client=r2_client,
            workspace_manager=workspace_manager,
            cleanup_after_processing=cleanup_after_processing
        )
        
        # Start the processing worker
        queue_manager.start_worker()
        
        logger.info("Services initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {str(e)}")
        return False


def validate_request_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize request data"""
    errors = []
    
    # Required fields
    required_fields = ['bucket_name']
    for field in required_fields:
        if field not in data or not data[field]:
            errors.append(f"Missing required field: {field}")
    
    # Validate bucket name
    if 'bucket_name' in data and len(data['bucket_name']) > 100:
        errors.append("Bucket name too long (max 100 characters)")
    
    # Validate numeric parameters
    try:
        if 'sample_guide_scale' in data:
            data['sample_guide_scale'] = float(data['sample_guide_scale'])
            if data['sample_guide_scale'] < 0 or data['sample_guide_scale'] > 20:
                errors.append("sample_guide_scale must be between 0 and 20")
    except ValueError:
        errors.append("sample_guide_scale must be a valid number")
    
    try:
        if 'sample_steps' in data:
            data['sample_steps'] = int(data['sample_steps'])
            if data['sample_steps'] < 1 or data['sample_steps'] > 100:
                errors.append("sample_steps must be between 1 and 100")
    except ValueError:
        errors.append("sample_steps must be a valid integer")
    
    # Validate size format
    if 'size' in data:
        size = data['size']
        if not isinstance(size, str) or '*' not in size:
            errors.append("size must be in format 'width*height'")
        else:
            try:
                width, height = size.split('*')
                width, height = int(width), int(height)
                if width < 64 or height < 64 or width > 2048 or height > 2048:
                    errors.append("size dimensions must be between 64 and 2048")
            except ValueError:
                errors.append("size must contain valid integer dimensions")
    
    if errors:
        return {'errors': errors}
    
    return {'data': data}


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Check if services are initialized
        if not queue_manager or not r2_client:
            return jsonify({
                'status': 'unhealthy',
                'message': 'Services not initialized',
                'timestamp': datetime.now().isoformat()
            }), 503
        
        # Get queue status
        queue_info = queue_manager.get_queue_info()
        
        return jsonify({
            'status': 'healthy',
            'message': 'Server is running',
            'timestamp': datetime.now().isoformat(),
            'queue_size': queue_info['queue_size'],
            'worker_running': queue_info['worker_running']
        })
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'message': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/<user_id>/<video_id>/<segment_id>', methods=['POST'])
def submit_request(user_id: str, video_id: str, segment_id: str):
    """Submit a new S2V processing request"""
    
    if not queue_manager:
        return jsonify({'error': 'Queue manager not initialized'}), 503
    
    try:
        # Validate user_id, video_id and segment_id
        if not user_id or not video_id or not segment_id:
            return jsonify({'error': 'Invalid user_id, video_id, or segment_id'}), 400
        
        if len(user_id) > 50 or len(video_id) > 50 or len(segment_id) > 50:
            return jsonify({'error': 'user_id, video_id, and segment_id must be 50 characters or less'}), 400
        
        # Check if request already exists
        existing_request = queue_manager.get_request_status(user_id, video_id, segment_id)
        if existing_request:
            return jsonify({
                'error': f'Request {user_id}/{video_id}/{segment_id} already exists',
                'status': existing_request.status.value,
                'existing_request': existing_request.to_dict()
            }), 409
        
        # Get and validate request data
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request must contain JSON data'}), 400
        
        validation_result = validate_request_data(data)
        if 'errors' in validation_result:
            return jsonify({
                'error': 'Invalid request data',
                'details': validation_result['errors']
            }), 400
        
        validated_data = validation_result['data']
        
        # Create processing request
        processing_request = ProcessingRequest(
            user_id=user_id,
            video_id=video_id,
            segment_id=segment_id,
            bucket_name=validated_data.get('bucket_name', 'dolphintest'),
            size=validated_data.get('size', '832*480'),
            sample_guide_scale=validated_data.get('sample_guide_scale', 4.0),
            sample_steps=validated_data.get('sample_steps', 20),
            ckpt_dir=validated_data.get('ckpt_dir', './Wan2.2-S2V-14B/')
        )
        
        # Add to queue
        if not queue_manager.add_request(processing_request):
            return jsonify({'error': 'Failed to add request to queue'}), 500
        
        # Return success response
        queue_info = queue_manager.get_queue_info()
        
        return jsonify({
            'message': f'Request {user_id}/{video_id}/{segment_id} queued successfully',
            'status': 'queued',
            'queue_position': processing_request.queue_position,
            'estimated_wait_time_minutes': processing_request.queue_position * 5,  # Rough estimate
            'queue_size': queue_info['queue_size'],
            'status_url': f'/{user_id}/{video_id}/{segment_id}/status',
            'created_time': processing_request.created_time
        }), 202
        
    except Exception as e:
        logger.error(f"Error submitting request {user_id}/{video_id}/{segment_id}: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@app.route('/<user_id>/<video_id>/<segment_id>/status', methods=['GET'])
def get_request_status(user_id: str, video_id: str, segment_id: str):
    """Get the status of a processing request"""
    
    if not queue_manager:
        return jsonify({'error': 'Queue manager not initialized'}), 503
    
    try:
        # Get request status
        request_info = queue_manager.get_request_status(user_id, video_id, segment_id)
        
        if not request_info:
            return jsonify({'error': f'Request {user_id}/{video_id}/{segment_id} not found'}), 404
        
        # Convert to dictionary for response
        status_dict = request_info.to_dict()
        
        # Add additional context
        queue_info = queue_manager.get_queue_info()
        status_dict['current_queue_size'] = queue_info['queue_size']
        
        # Calculate estimated completion time for queued requests
        if request_info.status == RequestStatus.QUEUED:
            estimated_minutes = request_info.queue_position * 5
            status_dict['estimated_completion_minutes'] = estimated_minutes
        
        return jsonify(status_dict)
        
    except Exception as e:
        logger.error(f"Error getting status for {user_id}/{video_id}/{segment_id}: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@app.route('/<user_id>/<video_id>/<segment_id>/result', methods=['GET'])
def get_request_result(user_id: str, video_id: str, segment_id: str):
    """Get the result of a completed processing request"""
    
    if not queue_manager:
        return jsonify({'error': 'Queue manager not initialized'}), 503
    
    try:
        # Get request status
        request_info = queue_manager.get_request_status(user_id, video_id, segment_id)
        
        if not request_info:
            return jsonify({'error': f'Request {user_id}/{video_id}/{segment_id} not found'}), 404
        
        # Check if request is completed
        if request_info.status != RequestStatus.COMPLETED:
            return jsonify({
                'error': f'Request not completed',
                'current_status': request_info.status.value,
                'message': request_info.message
            }), 400
        
        # Return result information
        result = {
            'user_id': user_id,
            'video_id': video_id,
            'segment_id': segment_id,
            'status': 'completed',
            'r2_output_path': request_info.r2_output_path,
            'public_url': request_info.public_url,
            'processing_time_minutes': None,
            'created_time': request_info.created_time,
            'completed_time': request_info.end_time
        }
        
        # Calculate processing time
        if request_info.start_time and request_info.end_time:
            start = datetime.fromisoformat(request_info.start_time.replace('Z', '+00:00'))
            end = datetime.fromisoformat(request_info.end_time.replace('Z', '+00:00'))
            processing_seconds = (end - start).total_seconds()
            result['processing_time_minutes'] = round(processing_seconds / 60, 2)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error getting result for {user_id}/{video_id}/{segment_id}: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@app.route('/queue', methods=['GET'])
def get_queue_status():
    """Get current queue status (for monitoring)"""
    
    if not queue_manager:
        return jsonify({'error': 'Queue manager not initialized'}), 503
    
    try:
        queue_info = queue_manager.get_queue_info()
        
        return jsonify({
            'timestamp': datetime.now().isoformat(),
            'queue_size': queue_info['queue_size'],
            'worker_running': queue_info['worker_running'],
            'current_processing': queue_info['current_processing'],
            'queued_requests': queue_info['queued_requests']
        })
        
    except Exception as e:
        logger.error(f"Error getting queue status: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@app.route('/requests', methods=['GET'])
def list_all_requests():
    """List all requests with their current status (for debugging/monitoring)"""
    
    if not queue_manager:
        return jsonify({'error': 'Queue manager not initialized'}), 503
    
    try:
        # Get all request statuses
        all_requests = []
        
        with queue_manager.status_lock:
            for request_key, request_info in queue_manager.request_status.items():
                all_requests.append(request_info.to_dict())
        
        # Sort by creation time
        all_requests.sort(key=lambda x: x.get('created_time', ''), reverse=True)
        
        return jsonify({
            'timestamp': datetime.now().isoformat(),
            'total_requests': len(all_requests),
            'requests': all_requests
        })
        
    except Exception as e:
        logger.error(f"Error listing requests: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({'error': 'Internal server error'}), 500


def shutdown_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, shutting down...")
    
    if queue_manager:
        logger.info("Stopping queue manager...")
        queue_manager.stop_worker()
    
    logger.info("Shutdown complete")
    sys.exit(0)


def main():
    """Main entry point"""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Wan S2V Flask API Server')
    parser.add_argument('--host', type=str, default='127.0.0.1',
                        help='Host to bind to (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=5000,
                        help='Port to bind to (default: 5000)')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug mode')
    parser.add_argument('--log-level', type=str, default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Set logging level (default: INFO)')
    
    args = parser.parse_args()
    
    # Set logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Register shutdown handlers
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    
    # Check for required environment variables
    required_env_vars = [
        'R2_ENDPOINT_URL',
        'R2_ACCESS_KEY_ID', 
        'R2_SECRET_ACCESS_KEY'
    ]
    
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        sys.exit(1)
    
    # Initialize services
    logger.info("Starting Wan S2V API Server...")
    if not initialize_services():
        logger.error("Failed to initialize services, exiting")
        sys.exit(1)
    
    logger.info(f"Server starting on {args.host}:{args.port}")
    logger.info(f"Debug mode: {args.debug}")
    logger.info(f"Log level: {args.log_level}")
    
    # Start Flask server
    try:
        app.run(
            host=args.host,
            port=args.port,
            debug=args.debug,
            threaded=True,
            use_reloader=False  # Disable reloader in production
        )
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
    finally:
        shutdown_handler(None, None)


if __name__ == '__main__':
    main()