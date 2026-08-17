"""
Test script for Overhaust API.
Sets up test data and tests the API endpoints.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from packages.memory.memory_store import get_memory_store
from packages.agent.autonomous_agent import get_overhaust_agent
import requests
import json

# Get the global memory store and agent (the same ones used by the API)
memory_store = get_memory_store()
agent = get_overhaust_agent()

# Add a test project
project_id = 'test-project-001'
memory_store.add_project(
    project_id,
    'Overhaust Test Project',
    'A test project for Overhaust',
    '/tmp/test-project'
)

# Add some test memories
memory_store.add_memory(
    project_id,
    'We decided to use React and TypeScript for the frontend',
    memory_type='permanent',
    importance_score=0.9,
    metadata={'knowledge_type': 'decision', 'source_type': 'conversation', 'source_title': 'Architecture Meeting'}
)

memory_store.add_memory(
    project_id,
    'The project is called Overhaust and helps AI agents be more efficient',
    memory_type='permanent',
    importance_score=0.8,
    metadata={'knowledge_type': 'project_identity', 'source_type': 'conversation', 'source_title': 'Project Kickoff'}
)

memory_store.add_memory(
    project_id,
    'We prefer to use FastAPI for the backend because it\'s fast and has good documentation.',
    memory_type='permanent',
    importance_score=0.85,
    metadata={'knowledge_type': 'preference', 'source_type': 'conversation', 'source_title': 'Backend Discussion'}
)

memory_store.add_memory(
    project_id,
    'There is an issue with the memory extraction being too slow.',
    memory_type='issue',
    importance_score=0.7,
    metadata={'knowledge_type': 'issue', 'source_type': 'conversation', 'source_title': 'Team Discussion'}
)

print('Project and memories added to memory store.')

# Now test the API endpoints
base_url = 'http://localhost:8000'

def test_endpoint(method, endpoint, data=None, description=''):
    """Helper function to test an endpoint and print results."""
    try:
        if method == 'GET':
            response = requests.get(f'{base_url}{endpoint}')
        elif method == 'POST':
            response = requests.post(f'{base_url}{endpoint}', json=data)
        else:
            raise ValueError(f'Unsupported method: {method}')
        
        print(f'\\n{description}')
        print(f'Endpoint: {endpoint}')
        print(f'Status Code: {response.status_code}')
        if response.status_code == 200:
            try:
                print('Response:', json.dumps(response.json(), indent=2))
            except:
                print('Response:', response.text)
        else:
            print('Error:', response.text)
        return response
    except Exception as e:
        print(f'\\n{description}')
        print(f'Endpoint: {endpoint}')
        print(f'Error: {e}')
        return None

# Test root endpoint
test_endpoint('GET', '/', None, 'Root endpoint:')

# Test health endpoint
test_endpoint('GET', '/health', None, 'Health endpoint:')

# Test understand-task endpoint
test_endpoint('POST', '/api/v1/understand-task', 
              {'project_id': project_id, 'task': 'How should we build the frontend?'}, 
              'Understand task endpoint:')

# Test get-context endpoint
test_endpoint('POST', '/api/v1/get-context', 
              {'project_id': project_id, 'task': 'What technology should we use for frontend?', 'max_knowledge_items': 5}, 
              'Get context endpoint:')

# Test estimate-tokens endpoint
test_endpoint('POST', '/api/v1/estimate-tokens', 
              {'text': 'Hello, world! This is a test.', 'model': 'gpt-4'}, 
              'Estimate tokens endpoint:')

# Test estimate-reduction endpoint
test_endpoint('POST', '/api/v1/estimate-reduction', 
              {
                  'original_text': 'This is a very long sentence that contains lots of information that might not be necessary for the AI to process. ' * 3,
                  'optimized_text': 'This is a test.',
                  'model': 'gpt-4'
              }, 
              'Estimate reduction endpoint:')

# Test search-knowledge endpoint
test_endpoint('POST', '/api/v1/search-knowledge', 
              {'project_id': project_id, 'query': 'frontend', 'limit': 5}, 
              'Search knowledge endpoint:')

# Test mark-resolved endpoint
test_endpoint('POST', '/api/v1/mark-resolved', 
              {'project_id': project_id, 'issue_description': 'Fixed the memory extraction speed issue'}, 
              'Mark resolved endpoint:')

# Test mark-stale endpoint (we need a memory ID to mark as stale)
# First, let's get a memory ID by searching for a memory
try:
    search_resp = requests.post(f'{base_url}/api/v1/search-knowledge', 
                                json={'project_id': project_id, 'query': 'React', 'limit': 1})
    if search_resp.status_code == 200:
        search_results = search_resp.json()
        if search_results.get('results') and len(search_results['results']) > 0:
            memory_id = search_results['results'][0]['id']
            test_endpoint('POST', '/api/v1/mark-stale', 
                          {'memory_id': memory_id, 'reason': 'Decision was revised in a later meeting'}, 
                          'Mark stale endpoint:')
        else:
            print('\\nMark stale endpoint:')
            print('No memories found to mark as stale.')
    else:
        print('\\nMark stale endpoint:')
        print('Error searching for memory:', search_resp.text)
except Exception as e:
    print('\\nMark stale endpoint:')
    print('Error:', e)

print('\\nAPI tests completed.')