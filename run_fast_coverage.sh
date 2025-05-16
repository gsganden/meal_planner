#!/usr/bin/env bash
set -uo pipefail

source .env

TEST_DIR="tests/"

SPECIFIC_EVAL_TEST_NODE_NAME_PATTERN="test_extract_recipe_name[tests/data/recipes/raw/good-old-fashioned-pancakes.html]"

PYTEST_K_EXPRESSION="${SPECIFIC_EVAL_TEST_NODE_NAME_PATTERN} or not test_main_evals"

#######################################################################################
# 1. Run the tests with coverage and capture exit status
#######################################################################################
uv run pytest \
  --cov=meal_planner \
  --cov-report=annotate \
  "$TEST_DIR" \
  -k "${PYTEST_K_EXPRESSION}" \
  --runslow
test_status=$?

#######################################################################################
# 2. Generate temp coverage files and show missing-line details if tests passed
#######################################################################################
if [ $test_status -eq 0 ] && [ -f .coverage ]; then
  echo -e "\nMissing‑line details:"
  grep -R --line-number '^!' --include='*.py,cover' . \
  | awk -F: '{sub(/,cover$/,"",$1); gsub(/^!/,"",$3); print $1 ":" $2 ": " $3}'
fi

#######################################################################################
# 3. Enforce coverage threshold
#######################################################################################
threshold=100
if [ $test_status -eq 0 ]; then
  uv run coverage report --fail-under=$threshold
  cov_status=$?            # 0 → met threshold, 2 → below
else
  cov_status=0             # we already know we'll exit with test failure
fi

#######################################################################################
# 4. Always clean up temp files
#######################################################################################
find . -name '*.py,cover' -delete
rm -f .coverage

#######################################################################################
# 5. Propagate the correct exit code
#######################################################################################
if [ $test_status -ne 0 ]; then
  exit $test_status         # tests failed
fi
exit $cov_status            # 0 if good, 2 if coverage too low
