#!/usr/bin/env python3
"""
Test script for the new Wan S2V API with {user_id}/{video_id}/{segment_id} structure
"""

import requests
import json
import time

# API configuration
API_BASE_URL = "http://localhost:5000"

def test_submit_request():
    """Test submitting a new S2V processing request"""
    
    # Example request parameters
    user_id = "user123"
    video_id = "video001"  
    segment_id = "segment001"
    
    # Request payload - just bucket name and optional parameters
    payload = {
        "bucket_name": "dolphintest",
        "size": "832*480",
        "sample_guide_scale": 4.0,
        "sample_steps": 20,
        "ckpt_dir": "./Wan2.2-S2V-14B/"
    }
    
    # Submit request
    url = f"{API_BASE_URL}/{user_id}/{video_id}/{segment_id}"
    
    print(f"Submitting request to: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    response = requests.post(url, json=payload)
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    return response.status_code == 202

def test_get_status():
    """Test getting request status"""
    
    user_id = "user123"
    video_id = "video001"
    segment_id = "segment001"
    
    url = f"{API_BASE_URL}/{user_id}/{video_id}/{segment_id}/status"
    
    print(f"\nGetting status from: {url}")
    
    response = requests.get(url)
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    return response.json() if response.status_code == 200 else None

def test_get_result():
    """Test getting request result"""
    
    user_id = "user123"
    video_id = "video001"
    segment_id = "segment001"
    
    url = f"{API_BASE_URL}/{user_id}/{video_id}/{segment_id}/result"
    
    print(f"\nGetting result from: {url}")
    
    response = requests.get(url)
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    return response.json() if response.status_code == 200 else None

def test_health_check():
    """Test server health"""
    
    url = f"{API_BASE_URL}/health"
    
    print(f"\nHealth check: {url}")
    
    response = requests.get(url)
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    return response.status_code == 200

def test_queue_status():
    """Test queue status"""
    
    url = f"{API_BASE_URL}/queue"
    
    print(f"\nQueue status: {url}")
    
    response = requests.get(url)
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    
    return response.json() if response.status_code == 200 else None

def main():
    """Main test function"""
    
    print("=" * 60)
    print("Testing Wan S2V API with new structure")
    print("=" * 60)
    
    # Test health check first
    if not test_health_check():
        print("ERROR: Server health check failed!")
        return
    
    # Test queue status
    test_queue_status()
    
    # Test submitting a request
    if test_submit_request():
        print("\n✅ Request submitted successfully!")
        
        # Wait a bit and check status
        time.sleep(1)
        status = test_get_status()
        
        if status and status.get('status') == 'completed':
            # If completed, get result
            result = test_get_result()
            if result:
                print("\n✅ Request completed and result retrieved!")
        else:
            print("\n📋 Request is still processing...")
    else:
        print("\n❌ Failed to submit request")
    
    print("\n" + "=" * 60)
    print("Test completed")
    print("=" * 60)

if __name__ == "__main__":
    main()