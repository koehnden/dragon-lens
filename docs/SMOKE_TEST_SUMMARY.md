# Smoke Tests Summary

## Overview

Smoke tests have been implemented to provide quick validation that all API endpoints are accessible and functioning at a basic level. These tests run through a complete workflow in logical order, checking status codes and basic response structures.

## What Are Smoke Tests?

Smoke tests are lightweight, high-level tests that answer the question: **"Does the system work at all?"**

They differ from unit and integration tests:
- **Unit Tests**: Test individual functions in isolation
- **Integration Tests**: Test components working together with detailed validation
- **Smoke Tests**: Quick checks that the entire system is operational

Think of smoke tests as a "sanity check" before running more comprehensive tests.

## Test Results

```
✅ 3 smoke tests passing
✅ Execution time: ~0.4s
✅ 100% pass rate
```

## Smoke Test Files

### `test_api_smoke.py`

Contains 3 main smoke test functions:

#### 1. `test_api_smoke_workflow`
**Complete end-to-end workflow through all API endpoints**

This test runs through the entire system in logical order:

```
Step 1: Create Vertical (SUV Cars)
  ↓ POST /api/v1/verticals
  ✓ Status: 201 Created
  ✓ Returns: vertical_id, name, description, created_at

Step 2: List Verticals
  ↓ GET /api/v1/verticals
  ✓ Status: 200 OK
  ✓ Verify: New vertical is present in list

Step 3: Get Vertical by ID
  ↓ GET /api/v1/verticals/{vertical_id}
  ✓ Status: 200 OK
  ✓ Verify: Details match created vertical

Step 4: Create Tracking Job
  ↓ POST /api/v1/tracking/jobs
  ✓ Status: 201 Created
  ✓ Uses: 2 brands (Toyota, Honda)
  ✓ Uses: 2 prompts (English + Chinese)
  ✓ Returns: run_id, vertical_id, model_name, status

Step 5: List Runs
  ↓ GET /api/v1/tracking/runs
  ✓ Status: 200 OK
  ✓ Verify: New run is present in list
  ↓ GET /api/v1/tracking/runs?vertical_id={vertical_id}
  ✓ Status: 200 OK
  ✓ Verify: Filtered list contains our run

Step 6: Get Run Details (with polling)
  ↓ GET /api/v1/tracking/runs/{run_id}
  ✓ Status: 200 OK
  ✓ Returns: run details with status
  ✓ Polls: Up to 3 times (simulated, short intervals)
  ✓ Verify: Status is pending/in_progress/completed/failed

Step 7: Get Latest Metrics
  ↓ GET /api/v1/metrics/latest?vertical_id={id}&model_name=qwen
  ✓ Status: 200 OK (or 404 if run not completed)
  ✓ Verify: Metrics structure if available

Step 8: Get Daily Metrics
  ↓ GET /api/v1/metrics/daily?vertical_id={id}&brand_id={id}&model_name=qwen
  ✓ Status: 200 OK
  ✓ Returns: Time series data (may be empty for new run)
```

**Sample Data Used**:
- Vertical: "SUV Cars - Smoke Test"
- Brands: Toyota (aliases: 丰田, Toyota Motors), Honda (aliases: 本田)
- Prompts:
  1. "What are the best SUV brands?" / "最好的SUV品牌是什么？"
  2. "Recommend a reliable SUV" / "推荐一款可靠的SUV"

#### 2. `test_health_endpoints_smoke`
**Quick health check for system status endpoints**

```
GET / (root)
  ✓ Status: 200 OK
  ✓ Returns: name, version, status

GET /health
  ✓ Status: 200 OK
  ✓ Returns: {"status": "healthy"}
```

#### 3. `test_error_handling_smoke`
**Verify error responses are working**

```
GET /api/v1/verticals/999999
  ✓ Status: 404 Not Found

GET /api/v1/tracking/runs/999999
  ✓ Status: 404 Not Found

GET /api/v1/metrics/latest?vertical_id=999999&model_name=qwen
  ✓ Status: 404 Not Found

POST /api/v1/verticals (duplicate)
  ✓ Status: 400 Bad Request
```

## Key Features

### 1. Comprehensive Coverage
Tests hit every major API endpoint in a single workflow:
- ✅ Verticals (create, list, get)
- ✅ Tracking Jobs (create)
- ✅ Runs (list, get, filter)
- ✅ Metrics (latest, daily)
- ✅ Health (root, health)
- ✅ Error handling (404, 400)

### 2. Logical Flow
Tests follow the natural user journey:
1. Set up structure (vertical)
2. Create tracking job
3. Monitor progress (runs)
4. View results (metrics)

### 3. Detailed Output
Tests print progress with `[SMOKE]` prefix for easy debugging:
```
[SMOKE] Step 1: Creating vertical...
[SMOKE] ✓ Vertical created with ID: 1
[SMOKE] Step 2: Listing verticals...
[SMOKE] ✓ Found 1 vertical(s)
...
[SMOKE] ✅ All smoke tests passed!
```

### 4. Fast Execution
Smoke tests run in ~0.4 seconds, making them ideal for:
- Pre-commit hooks
- CI/CD pipeline gates
- Quick local validation

### 5. Minimal Data
Uses small, realistic examples:
- 1 vertical
- 2 brands
- 2 prompts
- 1 model (qwen)

## Running Smoke Tests

```bash
# Run only smoke tests
poetry run pytest tests/smoke/ -v -s

# Run smoke tests without output capture (see print statements)
poetry run pytest tests/smoke/ -v -s

# Run smoke tests as part of full suite
poetry run pytest tests/ -v

# Run smoke tests in CI/CD (fail fast)
poetry run pytest tests/smoke/ --maxfail=1 -x
```

## When to Use Smoke Tests

### ✅ Good Use Cases:
1. **Before deploying** - Quick sanity check that nothing is broken
2. **After environment changes** - Verify system still works
3. **In CI/CD pipelines** - Fast gate before running full test suite
4. **After major refactoring** - Ensure basic functionality intact
5. **For new team members** - Demo of how the system works

### ❌ Not Suitable For:
1. Testing edge cases (use integration tests)
2. Testing complex business logic (use unit tests)
3. Testing error recovery (use integration tests)
4. Performance testing (use load tests)
5. Security testing (use security tests)

## Smoke Test vs Other Tests

| Aspect | Smoke Tests | Unit Tests | Integration Tests |
|--------|-------------|------------|-------------------|
| **Purpose** | "Does it work at all?" | "Does this function work?" | "Do components work together?" |
| **Scope** | Entire system | Single function | Multiple components |
| **Speed** | Fast (~0.4s) | Very fast (~0.3s) | Fast (~0.4s) |
| **Detail** | Status codes + basic structure | Detailed validation | Comprehensive validation |
| **Count** | 3 tests | 27 tests | 25 tests |
| **Run When** | Before deploy, in CI | Always | Always |

## Example Output

```
tests/smoke/test_api_smoke.py::test_api_smoke_workflow
[SMOKE] Step 1: Creating vertical...
[SMOKE] ✓ Vertical created with ID: 1
[SMOKE] Step 2: Listing verticals...
[SMOKE] ✓ Found 1 vertical(s)
[SMOKE] ✓ Created vertical present in list
[SMOKE] Step 3: Getting vertical 1...
[SMOKE] ✓ Retrieved vertical: SUV Cars - Smoke Test
[SMOKE] Step 4: Creating tracking job...
[SMOKE] ✓ Tracking job created with run ID: 1
[SMOKE] Step 5: Listing runs...
[SMOKE] ✓ Found 1 run(s)
[SMOKE] ✓ Created run present in list
[SMOKE] ✓ Found 1 run(s) for vertical 1
[SMOKE] Step 6: Getting run 1 details...
[SMOKE] ✓ Run status: pending
[SMOKE] ✓ Final run status after polling: pending
[SMOKE] Step 7: Getting latest metrics...
[SMOKE] ℹ Run not completed, skipping metrics validation (got 200)
[SMOKE] Step 8: Getting daily metrics...
[SMOKE] ✓ Retrieved daily metrics: 0 data point(s)

[SMOKE] ✅ All smoke tests passed!
[SMOKE] Summary:
  - Vertical ID: 1
  - Run ID: 1
  - Run Status: pending
  - All endpoints responded with expected status codes
PASSED
```

## Integration with CI/CD

### Example GitHub Actions Workflow

```yaml
name: Smoke Tests

on: [push, pull_request]

jobs:
  smoke-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install poetry
          poetry install
      - name: Run smoke tests
        run: poetry run pytest tests/smoke/ -v -s
```

### Pre-commit Hook

```bash
#!/bin/sh
# .git/hooks/pre-commit

echo "Running smoke tests..."
poetry run pytest tests/smoke/ -v
if [ $? -ne 0 ]; then
    echo "Smoke tests failed! Commit aborted."
    exit 1
fi
```

## Benefits

1. **Fast Feedback**: ~0.4s execution provides immediate validation
2. **High-Level Confidence**: Confirms entire system is operational
3. **Easy Debugging**: Clear output shows exactly where failures occur
4. **Documentation**: Tests serve as executable workflow documentation
5. **CI/CD Ready**: Perfect for automated pipelines

## Summary

✅ **3 smoke tests** covering all API endpoints
✅ **Complete workflow** from vertical creation to metrics
✅ **Fast execution** (~0.4 seconds)
✅ **Detailed output** with clear progress indicators
✅ **Minimal test data** (2 brands, 2 prompts)

The smoke tests provide a quick, reliable way to verify that the DragonLens API is operational and all endpoints are accessible!
