#!/usr/bin/env bash
set -uo pipefail

source .env

test_specs=(
  tests/test_main.py
  tests/test_api.py
  tests/test_database.py
  tests/services/test_recipe_processing.py
  tests/services/test_llm_service.py
  tests/services/test_text_processing.py
  # These tests are slow and cover the same codepaths with different inputs
  # to test LLM behavior. Here we run just one of them as a quick check that
  # the codepath is not broken and has full test coverage.
  "tests/test_main_evals.py::test_extract_recipe_name[tests/data/recipes/raw/good-old-fashioned-pancakes.html]"
)

#######################################################################################
# 1. Run the tests with coverage and capture exit status
#######################################################################################
uv run pytest \
  --cov=meal_planner \
  --cov-report=annotate \
  "${test_specs[@]}" \
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
