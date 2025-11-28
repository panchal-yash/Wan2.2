#!/usr/bin/env python3
"""
Test Client for Wan S2V Flask API Server

This script simulates a backend server making requests to the GPU server.
It demonstrates the complete workflow from request submission to result retrieval.
"""

import requests
import json
import time
import argparse
import sys
from datetime import datetime
from typing import Dict, Any, Optional


class WanAPIClient:
    """Client for interacting with the Wan S2V API"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:5000", timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()
    
    def health_check(self) -> Dict[str, Any]:
        """Check API server health"""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {'error': f'Health check failed: {str(e)}'}
        except Exception as e:
            return {'error': f'Unexpected error: {str(e)}'}
    
    def submit_request(self, user_id: str, request_id: str, 
                      prompt: str, image_r2_path: str, audio_r2_path: str,
                      **kwargs) -> Dict[str, Any]:
        """Submit a new processing request"""
        
        payload = {
            'prompt': prompt,
            'image_r2_path': image_r2_path,
            'audio_r2_path': audio_r2_path,
            **kwargs  # Additional parameters like size, sample_guide_scale, etc.
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/{user_id}/{request_id}",
                json=payload,
                timeout=self.timeout,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 202:
                return response.json()
            elif response.status_code == 409:
                return {'error': 'Request already exists', 'details': response.json()}
            else:
                response.raise_for_status()
                return {'error': f'Unexpected status code: {response.status_code}'}
                
        except requests.exceptions.RequestException as e:
            return {'error': f'Request submission failed: {str(e)}'}
        except Exception as e:
            return {'error': f'Unexpected error: {str(e)}'}
    
    def get_status(self, user_id: str, request_id: str) -> Dict[str, Any]:
        """Get request status"""
        try:
            response = self.session.get(
                f"{self.base_url}/{user_id}/{request_id}/status",
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return {'error': 'Request not found'}
            else:
                response.raise_for_status()
                return {'error': f'Unexpected status code: {response.status_code}'}
                
        except requests.exceptions.RequestException as e:
            return {'error': f'Status check failed: {str(e)}'}
        except Exception as e:
            return {'error': f'Unexpected error: {str(e)}'}
    
    def get_result(self, user_id: str, request_id: str) -> Dict[str, Any]:
        """Get request result"""
        try:
            response = self.session.get(
                f"{self.base_url}/{user_id}/{request_id}/result",
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return {'error': 'Request not found'}
            elif response.status_code == 400:
                return {'error': 'Request not completed', 'details': response.json()}
            else:
                response.raise_for_status()
                return {'error': f'Unexpected status code: {response.status_code}'}
                
        except requests.exceptions.RequestException as e:
            return {'error': f'Result retrieval failed: {str(e)}'}
        except Exception as e:
            return {'error': f'Unexpected error: {str(e)}'}
    
    def get_queue_info(self) -> Dict[str, Any]:
        """Get current queue information"""
        try:
            response = self.session.get(f"{self.base_url}/queue", timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {'error': f'Queue info failed: {str(e)}'}
    
    def list_all_requests(self) -> Dict[str, Any]:
        """List all requests"""
        try:
            response = self.session.get(f"{self.base_url}/requests", timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {'error': f'List requests failed: {str(e)}'}


def poll_until_complete(client: WanAPIClient, user_id: str, request_id: str, 
                       poll_interval: int = 10, max_wait: int = 3600) -> Dict[str, Any]:
    """Poll request status until completion or timeout"""
    
    print(f"Polling status for {user_id}/{request_id}...")
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        status = client.get_status(user_id, request_id)
        
        if 'error' in status:
            return status
        
        current_status = status.get('status', 'unknown')
        message = status.get('message', '')
        progress = status.get('progress', 0)
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Status: {current_status} - {message} ({progress}%)")
        
        if current_status == 'completed':
            return status
        elif current_status in ['failed', 'failed_download', 'failed_processing', 'failed_upload']:
            return status
        
        # Show queue position for queued requests
        if current_status == 'queued':
            queue_pos = status.get('queue_position', 0)
            estimated_wait = status.get('estimated_completion_minutes', 0)
            print(f"    Queue position: {queue_pos}, Estimated wait: {estimated_wait} minutes")
        
        time.sleep(poll_interval)
    
    return {'error': 'Polling timed out'}


def run_test_scenario(client: WanAPIClient, scenario: Dict[str, Any]) -> bool:
    """Run a single test scenario"""
    
    print(f"\n{'='*60}")
    print(f"Running scenario: {scenario['name']}")
    print(f"{'='*60}")
    
    user_id = scenario['user_id']
    request_id = scenario['request_id']
    
    # Submit request
    print(f"Submitting request {user_id}/{request_id}...")
    submit_result = client.submit_request(
        user_id=user_id,
        request_id=request_id,
        prompt=scenario['prompt'],
        image_r2_path=scenario['image_r2_path'],
        audio_r2_path=scenario['audio_r2_path'],
        **scenario.get('params', {})
    )
    
    if 'error' in submit_result:
        print(f"❌ Request submission failed: {submit_result['error']}")
        return False
    
    print(f"✅ Request submitted successfully")
    print(f"   Queue position: {submit_result.get('queue_position', 'unknown')}")
    print(f"   Estimated wait: {submit_result.get('estimated_wait_time_minutes', 'unknown')} minutes")
    
    # Poll until completion
    final_status = poll_until_complete(
        client, user_id, request_id, 
        poll_interval=scenario.get('poll_interval', 10),
        max_wait=scenario.get('max_wait', 3600)
    )
    
    if 'error' in final_status:
        print(f"❌ Polling failed: {final_status['error']}")
        return False
    
    # Check final result
    if final_status.get('status') == 'completed':
        print(f"✅ Request completed successfully!")
        
        # Get result details
        result = client.get_result(user_id, request_id)
        if 'error' not in result:
            print(f"   R2 Output: {result.get('r2_output_path', 'unknown')}")
            if result.get('public_url'):
                print(f"   Public URL: {result['public_url']}")
            print(f"   Processing time: {result.get('processing_time_minutes', 'unknown')} minutes")
        else:
            print(f"⚠️  Could not retrieve result details: {result['error']}")
        
        return True
    else:
        print(f"❌ Request failed: {final_status.get('status', 'unknown')}")
        error_details = final_status.get('error_details', 'No error details available')
        print(f"   Error: {error_details}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Wan S2V API Test Client')
    parser.add_argument('--server', type=str, default='http://127.0.0.1:5000',
                        help='API server URL (default: http://127.0.0.1:5000)')
    parser.add_argument('--timeout', type=int, default=30,
                        help='Request timeout in seconds (default: 30)')
    parser.add_argument('--health-only', action='store_true',
                        help='Only run health check')
    parser.add_argument('--queue-info', action='store_true',
                        help='Show queue information')
    parser.add_argument('--list-requests', action='store_true',
                        help='List all requests')
    
    args = parser.parse_args()
    
    # Create client
    client = WanAPIClient(base_url=args.server, timeout=args.timeout)
    
    # Health check
    print("Checking API server health...")
    health = client.health_check()
    if 'error' in health:
        print(f"❌ Health check failed: {health['error']}")
        sys.exit(1)
    else:
        print(f"✅ Server is healthy")
        print(f"   Status: {health.get('status', 'unknown')}")
        print(f"   Queue size: {health.get('queue_size', 'unknown')}")
        print(f"   Worker running: {health.get('worker_running', 'unknown')}")
    
    if args.health_only:
        return
    
    # Show queue info if requested
    if args.queue_info:
        print("\nQueue Information:")
        queue_info = client.get_queue_info()
        if 'error' not in queue_info:
            print(json.dumps(queue_info, indent=2))
        else:
            print(f"❌ {queue_info['error']}")
        return
    
    # List all requests if requested
    if args.list_requests:
        print("\nAll Requests:")
        all_requests = client.list_all_requests()
        if 'error' not in all_requests:
            print(json.dumps(all_requests, indent=2))
        else:
            print(f"❌ {all_requests['error']}")
        return
    
    # Define test scenarios
    test_scenarios = [
        {
            'name': 'Basic S2V Test',
            'user_id': 'test_user_001',
            'request_id': f'req_{int(time.time())}',
            'prompt': 'A beautiful sunset over the ocean with gentle waves',
            'image_r2_path': 'input-bucket/images/test/sunset.jpg',
            'audio_r2_path': 'input-bucket/audio/test/ocean_waves.wav',
            'params': {
                'size': '832*480',
                'sample_guide_scale': 4.0,
                'sample_steps': 20
            },
            'poll_interval': 10,
            'max_wait': 1800  # 30 minutes
        }
    ]
    
    # Run test scenarios
    success_count = 0
    total_scenarios = len(test_scenarios)
    
    for scenario in test_scenarios:
        if run_test_scenario(client, scenario):
            success_count += 1
    
    # Summary
    print(f"\n{'='*60}")
    print(f"TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Successful: {success_count}/{total_scenarios}")
    print(f"Failed: {total_scenarios - success_count}/{total_scenarios}")
    
    if success_count == total_scenarios:
        print("🎉 All tests passed!")
        sys.exit(0)
    else:
        print("❌ Some tests failed")
        sys.exit(1)


if __name__ == '__main__':
    main()