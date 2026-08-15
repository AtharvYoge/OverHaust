"""Comprehensive backend API tests for OverHaust Context Runtime."""
import requests
import sys
import time
from datetime import datetime

BASE_URL = "https://ai-context-1.preview.emergentagent.com/api"
TEST_EMAIL = "qa-tester@overhaust.com"

class ContextRuntimeTester:
    def __init__(self):
        self.token = None
        self.user_id = None
        self.project_id = None
        self.labkot_project_id = None
        self.context_source_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failed_tests = []

    def log(self, msg, level="INFO"):
        print(f"[{level}] {msg}")

    def run_test(self, name, method, endpoint, expected_status, data=None, timeout=120):
        """Run a single API test with long timeout for LLM operations."""
        url = f"{BASE_URL}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        self.log(f"\n{'='*60}")
        self.log(f"Test #{self.tests_run}: {name}")
        self.log(f"{'='*60}")
        
        try:
            start = time.time()
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=timeout)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=timeout)
            
            elapsed = time.time() - start
            
            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"✅ PASSED - Status: {response.status_code} (took {elapsed:.2f}s)", "PASS")
                try:
                    resp_json = response.json()
                    self.log(f"Response preview: {str(resp_json)[:200]}...")
                    return True, resp_json
                except Exception:
                    return True, {}
            else:
                self.tests_failed += 1
                self.failed_tests.append(name)
                self.log(f"❌ FAILED - Expected {expected_status}, got {response.status_code}", "FAIL")
                try:
                    self.log(f"Response: {response.text[:500]}", "FAIL")
                except Exception:
                    pass
                return False, {}

        except requests.exceptions.Timeout:
            self.tests_failed += 1
            self.failed_tests.append(name)
            self.log(f"❌ FAILED - Request timeout after {timeout}s", "FAIL")
            return False, {}
        except Exception as e:
            self.tests_failed += 1
            self.failed_tests.append(name)
            self.log(f"❌ FAILED - Error: {str(e)}", "FAIL")
            return False, {}

    # ===== AUTH TESTS =====
    
    def test_login(self):
        """Test POST /api/auth/login with email returns token and user."""
        success, response = self.run_test(
            "Auth: Login with email",
            "POST",
            "/auth/login",
            200,
            data={"email": TEST_EMAIL}
        )
        if success and 'token' in response and 'user' in response:
            self.token = response['token']
            self.user_id = response['user'].get('id')
            self.log(f"✓ Token acquired: {self.token[:20]}...")
            self.log(f"✓ User ID: {self.user_id}")
            return True
        return False

    def test_me_with_token(self):
        """Test GET /api/auth/me with Bearer token returns current user."""
        success, response = self.run_test(
            "Auth: Get current user with token",
            "GET",
            "/auth/me",
            200
        )
        if success and response.get('email') == TEST_EMAIL:
            self.log(f"✓ User email verified: {response.get('email')}")
            return True
        return False

    def test_me_without_token(self):
        """Test GET /api/auth/me without token returns 401."""
        saved_token = self.token
        self.token = None
        success, _ = self.run_test(
            "Auth: Get current user without token (expect 401)",
            "GET",
            "/auth/me",
            401
        )
        self.token = saved_token
        return success

    # ===== PROJECT TESTS =====

    def test_create_project(self):
        """Test POST /api/projects creates a new project."""
        success, response = self.run_test(
            "Projects: Create new project",
            "POST",
            "/projects",
            200,
            data={
                "name": f"Test Project {datetime.now().strftime('%H%M%S')}",
                "description": "A test project for QA",
                "stack": ["React", "FastAPI", "MongoDB"]
            }
        )
        if success and 'id' in response:
            self.project_id = response['id']
            self.log(f"✓ Project created with ID: {self.project_id}")
            return True
        return False

    def test_list_projects(self):
        """Test GET /api/projects lists user's projects."""
        success, response = self.run_test(
            "Projects: List all projects",
            "GET",
            "/projects",
            200
        )
        if success and isinstance(response, list):
            self.log(f"✓ Found {len(response)} project(s)")
            return True
        return False

    def test_get_project(self):
        """Test GET /api/projects/:id returns single project."""
        if not self.project_id:
            self.log("⚠ Skipping - no project_id available", "WARN")
            return False
        success, response = self.run_test(
            "Projects: Get single project by ID",
            "GET",
            f"/projects/{self.project_id}",
            200
        )
        if success and response.get('id') == self.project_id:
            self.log(f"✓ Project retrieved: {response.get('name')}")
            return True
        return False

    def test_seed_labkot(self):
        """Test POST /api/projects/seed/labkot seeds preloaded LabKOT project."""
        success, response = self.run_test(
            "Projects: Seed LabKOT demo project",
            "POST",
            "/projects/seed/labkot",
            200
        )
        if success and 'id' in response and response.get('name') == 'LabKOT':
            self.labkot_project_id = response['id']
            self.log(f"✓ LabKOT project seeded with ID: {self.labkot_project_id}")
            return True
        return False

    # ===== CONTEXT SOURCE TESTS =====

    def test_add_context_source(self):
        """Test POST /api/projects/:id/contexts adds a context source."""
        if not self.project_id:
            self.log("⚠ Skipping - no project_id available", "WARN")
            return False
        success, response = self.run_test(
            "Contexts: Add context source",
            "POST",
            f"/projects/{self.project_id}/contexts",
            200,
            data={
                "type": "note",
                "name": "Test Note",
                "content": "This is a test context source for the QA project. It contains important information about the testing process."
            }
        )
        if success and 'id' in response:
            self.context_source_id = response['id']
            self.log(f"✓ Context source added with ID: {self.context_source_id}")
            return True
        return False

    def test_list_contexts(self):
        """Test GET /api/projects/:id/contexts lists sources."""
        if not self.project_id:
            self.log("⚠ Skipping - no project_id available", "WARN")
            return False
        success, response = self.run_test(
            "Contexts: List all context sources",
            "GET",
            f"/projects/{self.project_id}/contexts",
            200
        )
        if success and isinstance(response, list):
            self.log(f"✓ Found {len(response)} context source(s)")
            return True
        return False

    def test_list_labkot_contexts(self):
        """Test GET /api/projects/:id/contexts for LabKOT (should have 9 sources)."""
        if not self.labkot_project_id:
            self.log("⚠ Skipping - no labkot_project_id available", "WARN")
            return False
        success, response = self.run_test(
            "Contexts: List LabKOT context sources (expect 9)",
            "GET",
            f"/projects/{self.labkot_project_id}/contexts",
            200
        )
        if success and isinstance(response, list):
            count = len(response)
            self.log(f"✓ LabKOT has {count} context source(s)")
            if count == 9:
                self.log("✓ Correct count: 9 sources (6 files + 2 docs + 1 conversation)")
                return True
            else:
                self.log(f"⚠ Expected 9 sources, got {count}", "WARN")
                return False
        return False

    # ===== CACHE BUILD TESTS =====

    def test_build_cache_labkot(self):
        """Test POST /api/projects/:id/cache/build calls LLM and returns CacheDocument."""
        if not self.labkot_project_id:
            self.log("⚠ Skipping - no labkot_project_id available", "WARN")
            return False
        
        self.log("⏳ Building cache (this may take 6-15 seconds)...")
        success, response = self.run_test(
            "Cache: Build context cache for LabKOT (LLM call)",
            "POST",
            f"/projects/{self.labkot_project_id}/cache/build",
            200,
            timeout=60  # Long timeout for LLM
        )
        
        if not success:
            return False
        
        # Validate response structure
        checks = []
        
        # Check cache structure
        if 'cache' in response:
            cache = response['cache']
            checks.append(('cache.project_identity', 'project_identity' in cache))
            checks.append(('cache.architecture', 'architecture' in cache))
            checks.append(('cache.components', 'components' in cache))
            checks.append(('cache.decisions', 'decisions' in cache))
            checks.append(('cache.current_state', 'current_state' in cache))
            checks.append(('cache.conversation_memory', 'conversation_memory' in cache))
            
            # Check current_state sub-lists
            if 'current_state' in cache:
                cs = cache['current_state']
                checks.append(('current_state.implemented', 'implemented' in cs))
                checks.append(('current_state.in_progress', 'in_progress' in cs))
                checks.append(('current_state.known_issues', 'known_issues' in cs))
            
            # Check conversation_memory buckets
            if 'conversation_memory' in cache:
                cm = cache['conversation_memory']
                checks.append(('conversation_memory.permanent_knowledge', 'permanent_knowledge' in cm))
                checks.append(('conversation_memory.temporary_task_context', 'temporary_task_context' in cm))
                checks.append(('conversation_memory.resolved_issues', 'resolved_issues' in cm))
                checks.append(('conversation_memory.rejected_approaches', 'rejected_approaches' in cm))
                checks.append(('conversation_memory.open_issues', 'open_issues' in cm))
        
        # Check metrics
        if 'metrics' in response:
            metrics = response['metrics']
            checks.append(('metrics.raw_tokens', 'raw_tokens' in metrics))
            checks.append(('metrics.cache_tokens', 'cache_tokens' in metrics))
            checks.append(('metrics.reduction_pct', 'reduction_pct' in metrics))
            checks.append(('metrics.knowledge_items', 'knowledge_items' in metrics))
            
            # Validate reduction > 50% for LabKOT
            reduction = metrics.get('reduction_pct', 0)
            checks.append(('reduction_pct > 50%', reduction > 50))
            
            # Validate knowledge_items > 0
            knowledge = metrics.get('knowledge_items', 0)
            checks.append(('knowledge_items > 0', knowledge > 0))
            
            self.log(f"✓ Metrics: reduction={reduction}%, knowledge_items={knowledge}")
        
        # Print all checks
        all_passed = True
        for check_name, check_result in checks:
            if check_result:
                self.log(f"  ✓ {check_name}")
            else:
                self.log(f"  ✗ {check_name}", "WARN")
                all_passed = False
        
        return all_passed

    def test_get_latest_cache(self):
        """Test GET /api/projects/:id/cache returns latest cache."""
        if not self.labkot_project_id:
            self.log("⚠ Skipping - no labkot_project_id available", "WARN")
            return False
        success, response = self.run_test(
            "Cache: Get latest cache",
            "GET",
            f"/projects/{self.labkot_project_id}/cache",
            200
        )
        if success and response and 'cache' in response:
            self.log(f"✓ Latest cache retrieved (version {response.get('version', 1)})")
            return True
        return False

    def test_get_cache_history(self):
        """Test GET /api/projects/:id/cache/history returns list."""
        if not self.labkot_project_id:
            self.log("⚠ Skipping - no labkot_project_id available", "WARN")
            return False
        success, response = self.run_test(
            "Cache: Get cache history",
            "GET",
            f"/projects/{self.labkot_project_id}/cache/history",
            200
        )
        if success and isinstance(response, list):
            self.log(f"✓ Cache history retrieved ({len(response)} version(s))")
            return True
        return False

    def test_get_incremental_status(self):
        """Test GET /api/projects/:id/cache/incremental returns needs_rebuild status."""
        if not self.labkot_project_id:
            self.log("⚠ Skipping - no labkot_project_id available", "WARN")
            return False
        success, response = self.run_test(
            "Cache: Get incremental status",
            "GET",
            f"/projects/{self.labkot_project_id}/cache/incremental",
            200
        )
        if success and 'needs_rebuild' in response:
            self.log(f"✓ Incremental status: needs_rebuild={response.get('needs_rebuild')}")
            return True
        return False

    # ===== TASK TESTS =====

    def test_create_task(self):
        """Test POST /api/projects/:id/tasks calls LLM and returns TaskRun."""
        if not self.labkot_project_id:
            self.log("⚠ Skipping - no labkot_project_id available", "WARN")
            return False
        
        self.log("⏳ Generating task context (this may take 4-10 seconds)...")
        success, response = self.run_test(
            "Tasks: Create task and generate context (LLM call)",
            "POST",
            f"/projects/{self.labkot_project_id}/tasks",
            200,
            data={
                "description": "Fix the WebSocket reconnection delay issue - reduce initial backoff from 5s to 250ms and cap at 5s instead of 60s"
            },
            timeout=60  # Long timeout for LLM
        )
        
        if not success:
            return False
        
        # Validate response structure
        checks = []
        
        # Check selection structure
        if 'selection' in response:
            sel = response['selection']
            checks.append(('selection.relevant', 'relevant' in sel))
            checks.append(('selection.ignored', 'ignored' in sel))
            checks.append(('selection.assembled_context', 'assembled_context' in sel))
            
            # Check assembled_context is non-empty
            assembled = sel.get('assembled_context', '')
            checks.append(('assembled_context non-empty', len(assembled) > 0))
            
            # Check relevant has expected keys
            if 'relevant' in sel:
                rel = sel['relevant']
                checks.append(('relevant.components', 'components' in rel))
                checks.append(('relevant.architecture_keys', 'architecture_keys' in rel))
                checks.append(('relevant.decisions', 'decisions' in rel))
                checks.append(('relevant.conversation_memory', 'conversation_memory' in rel))
        
        # Check metrics
        if 'metrics' in response:
            metrics = response['metrics']
            checks.append(('metrics.original_tokens', 'original_tokens' in metrics))
            checks.append(('metrics.optimized_tokens', 'optimized_tokens' in metrics))
            checks.append(('metrics.reduction_pct', 'reduction_pct' in metrics))
            
            orig = metrics.get('original_tokens', 0)
            opt = metrics.get('optimized_tokens', 0)
            red = metrics.get('reduction_pct', 0)
            self.log(f"✓ Metrics: original={orig}, optimized={opt}, reduction={red}%")
        
        # Print all checks
        all_passed = True
        for check_name, check_result in checks:
            if check_result:
                self.log(f"  ✓ {check_name}")
            else:
                self.log(f"  ✗ {check_name}", "WARN")
                all_passed = False
        
        return all_passed

    # ===== ANALYTICS TESTS =====

    def test_analytics_summary(self):
        """Test GET /api/analytics returns AnalyticsSummary with connected_agents."""
        success, response = self.run_test(
            "Analytics: Get summary",
            "GET",
            "/analytics",
            200
        )
        
        if not success:
            return False
        
        # Validate response structure (including NEW connected_agents field)
        checks = [
            ('projects', 'projects' in response),
            ('total_raw_tokens', 'total_raw_tokens' in response),
            ('total_cache_tokens', 'total_cache_tokens' in response),
            ('avg_reduction_pct', 'avg_reduction_pct' in response),
            ('total_tasks', 'total_tasks' in response),
            ('total_cache_builds', 'total_cache_builds' in response),
            ('estimated_context_saved', 'estimated_context_saved' in response),
            ('knowledge_items', 'knowledge_items' in response),
            ('connected_agents', 'connected_agents' in response),  # NEW field
        ]
        
        all_passed = True
        for check_name, check_result in checks:
            if check_result:
                self.log(f"  ✓ {check_name}: {response.get(check_name)}")
            else:
                self.log(f"  ✗ {check_name}", "WARN")
                all_passed = False
        
        return all_passed

    # ===== CONNECTIONS TESTS (NEW) =====

    def test_connections_catalog(self):
        """Test GET /api/connections/catalog returns agent list with statuses."""
        success, response = self.run_test(
            "Connections: Get catalog (no auth required)",
            "GET",
            "/connections/catalog",
            200
        )
        
        if not success:
            return False
        
        # Validate response is a list of agents
        if not isinstance(response, list):
            self.log("✗ Response is not a list", "WARN")
            return False
        
        self.log(f"✓ Catalog has {len(response)} agents")
        
        # Validate each agent has required fields
        required_fields = ['key', 'name', 'category', 'status']
        all_passed = True
        
        for agent in response:
            for field in required_fields:
                if field not in agent:
                    self.log(f"✗ Agent missing field: {field}", "WARN")
                    all_passed = False
        
        # Check for specific agents mentioned in requirements
        agent_keys = [a.get('key') for a in response]
        expected_agents = ['cursor', 'claude', 'chatgpt', 'gemini', 'claude_code', 'replit']
        for expected in expected_agents:
            if expected in agent_keys:
                self.log(f"  ✓ Found agent: {expected}")
            else:
                self.log(f"  ✗ Missing agent: {expected}", "WARN")
                all_passed = False
        
        # Verify gemini has status 'coming_soon'
        gemini = next((a for a in response if a.get('key') == 'gemini'), None)
        if gemini:
            if gemini.get('status') == 'coming_soon':
                self.log("  ✓ Gemini has status 'coming_soon'")
            else:
                self.log(f"  ✗ Gemini status is '{gemini.get('status')}', expected 'coming_soon'", "WARN")
                all_passed = False
        
        return all_passed

    def test_list_connections_empty(self):
        """Test GET /api/connections returns empty list initially."""
        success, response = self.run_test(
            "Connections: List user connections (expect empty initially)",
            "GET",
            "/connections",
            200
        )
        
        if success and isinstance(response, list):
            self.log(f"✓ User has {len(response)} connection(s)")
            return True
        return False

    def test_create_connection_available(self):
        """Test POST /api/connections creates connection for 'available' agent."""
        success, response = self.run_test(
            "Connections: Create connection (cursor - available)",
            "POST",
            "/connections",
            200,
            data={
                "agent_key": "cursor",
                "agent_name": "Cursor"
            }
        )
        
        if success and 'id' in response:
            self.connection_id = response['id']
            self.log(f"✓ Connection created with ID: {self.connection_id}")
            self.log(f"✓ Agent: {response.get('agent_name')}, Status: {response.get('status')}")
            return True
        return False

    def test_create_connection_coming_soon(self):
        """Test POST /api/connections rejects 'coming_soon' agent with 400."""
        success, response = self.run_test(
            "Connections: Create connection (gemini - coming_soon, expect 400)",
            "POST",
            "/connections",
            400,  # Expect rejection
            data={
                "agent_key": "gemini",
                "agent_name": "Gemini"
            }
        )
        
        if success:
            self.log("✓ Correctly rejected 'coming_soon' agent with 400")
            return True
        return False

    def test_list_connections_after_create(self):
        """Test GET /api/connections returns created connection."""
        success, response = self.run_test(
            "Connections: List user connections (expect 1 after create)",
            "GET",
            "/connections",
            200
        )
        
        if success and isinstance(response, list):
            count = len(response)
            self.log(f"✓ User has {count} connection(s)")
            if count >= 1:
                conn = response[0]
                self.log(f"  ✓ Connection: {conn.get('agent_name')} ({conn.get('agent_key')})")
                return True
            else:
                self.log("  ✗ Expected at least 1 connection", "WARN")
                return False
        return False

    def test_delete_connection(self):
        """Test DELETE /api/connections/:id removes connection."""
        if not hasattr(self, 'connection_id') or not self.connection_id:
            self.log("⚠ Skipping - no connection_id available", "WARN")
            return False
        
        success, _ = self.run_test(
            "Connections: Delete connection",
            "DELETE",
            f"/connections/{self.connection_id}",
            200
        )
        return success

    # ===== USAGE / PLAN ADVISOR TESTS (NEW) =====

    def test_usage_plan_advisor(self):
        """Test GET /api/usage/plan-advisor returns PlanAdvice with estimates."""
        success, response = self.run_test(
            "Usage: Get plan advisor",
            "GET",
            "/usage/plan-advisor",
            200
        )
        
        if not success:
            return False
        
        # Validate response structure
        required_fields = [
            'plan_name',
            'current_usage_pct',
            'unnecessary_pct',
            'optimized_usage_pct',
            'estimated_reduction_pct',
            'recommendation',
            'can_stay_on_plan',
            'original_tokens',
            'optimized_tokens',
            'information_saved_tokens',
            'disclaimer'
        ]
        
        all_passed = True
        for field in required_fields:
            if field in response:
                value = response[field]
                self.log(f"  ✓ {field}: {value if not isinstance(value, str) or len(str(value)) < 60 else str(value)[:60] + '...'}")
            else:
                self.log(f"  ✗ Missing field: {field}", "WARN")
                all_passed = False
        
        # Validate percentages are in valid range
        if 'current_usage_pct' in response:
            pct = response['current_usage_pct']
            if 0 <= pct <= 100:
                self.log(f"  ✓ current_usage_pct in valid range: {pct}%")
            else:
                self.log(f"  ✗ current_usage_pct out of range: {pct}%", "WARN")
                all_passed = False
        
        if 'estimated_reduction_pct' in response:
            pct = response['estimated_reduction_pct']
            if 0 <= pct <= 100:
                self.log(f"  ✓ estimated_reduction_pct in valid range: {pct}%")
            else:
                self.log(f"  ✗ estimated_reduction_pct out of range: {pct}%", "WARN")
                all_passed = False
        
        # Validate disclaimer mentions "estimates"
        if 'disclaimer' in response:
            disclaimer = response['disclaimer'].lower()
            if 'estimate' in disclaimer:
                self.log("  ✓ Disclaimer mentions 'estimates'")
            else:
                self.log("  ✗ Disclaimer should mention 'estimates'", "WARN")
                all_passed = False
        
        return all_passed

    # ===== DELETE TESTS =====

    def test_delete_context_source(self):
        """Test DELETE /api/projects/:id/contexts/:sid removes source."""
        if not self.project_id or not self.context_source_id:
            self.log("⚠ Skipping - no project_id or context_source_id available", "WARN")
            return False
        success, _ = self.run_test(
            "Contexts: Delete context source",
            "DELETE",
            f"/projects/{self.project_id}/contexts/{self.context_source_id}",
            200
        )
        return success

    def test_delete_project(self):
        """Test DELETE /api/projects/:id removes project and cascades."""
        if not self.project_id:
            self.log("⚠ Skipping - no project_id available", "WARN")
            return False
        success, _ = self.run_test(
            "Projects: Delete project (cascade contexts/cache/tasks)",
            "DELETE",
            f"/projects/{self.project_id}",
            200
        )
        return success

    # ===== RUN ALL TESTS =====

    def run_all(self):
        """Run all tests in sequence."""
        self.log("\n" + "="*60)
        self.log("OVERHAUST CONTEXT RUNTIME - BACKEND API TESTS")
        self.log("="*60 + "\n")
        
        # Auth tests
        if not self.test_login():
            self.log("❌ Login failed - cannot proceed with other tests", "FAIL")
            return False
        
        self.test_me_with_token()
        self.test_me_without_token()
        
        # Connections tests (NEW - test before creating projects to verify catalog works without auth)
        self.test_connections_catalog()
        self.test_list_connections_empty()
        self.test_create_connection_available()
        self.test_create_connection_coming_soon()
        self.test_list_connections_after_create()
        
        # Project tests
        self.test_create_project()
        self.test_list_projects()
        self.test_get_project()
        self.test_seed_labkot()
        
        # Context source tests
        self.test_add_context_source()
        self.test_list_contexts()
        self.test_list_labkot_contexts()
        
        # Cache tests (using LabKOT)
        self.test_build_cache_labkot()
        self.test_get_latest_cache()
        self.test_get_cache_history()
        self.test_get_incremental_status()
        
        # Task tests (using LabKOT)
        self.test_create_task()
        
        # Analytics tests (includes connected_agents count)
        self.test_analytics_summary()
        
        # Usage / Plan advisor tests (NEW)
        self.test_usage_plan_advisor()
        
        # Delete tests
        self.test_delete_connection()
        self.test_delete_context_source()
        self.test_delete_project()
        
        # Summary
        self.log("\n" + "="*60)
        self.log("TEST SUMMARY")
        self.log("="*60)
        self.log(f"Total tests run: {self.tests_run}")
        self.log(f"✅ Passed: {self.tests_passed}")
        self.log(f"❌ Failed: {self.tests_failed}")
        
        if self.tests_failed > 0:
            self.log("\nFailed tests:")
            for test_name in self.failed_tests:
                self.log(f"  - {test_name}", "FAIL")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        self.log(f"\nSuccess rate: {success_rate:.1f}%")
        
        return self.tests_failed == 0


def main():
    tester = ContextRuntimeTester()
    success = tester.run_all()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
