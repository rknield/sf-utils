# Function to parse JSON without jq (basic bash parsing)
parse_json_basic() {
    local json_file="$1"
    local field="$2"
    
    # Basic grep/sed parsing for simple JSON fields
    grep "\"$field\"" "$json_file" | sed 's/.*"'$field'"[[:space:]]*:[[:space:]]*"\?//' | sed 's/"\?,\?$//' | head -1
}

# Function to count JSON records without jq
count_json_records() {
    local json_file="$1"
    
    # Count occurrences of record separators or Id fields
    grep -c '"Id"' "$json_file" 2>/dev/null || echo "0"
}

# Function to extract simple values from JSON
extract_json_values() {
    local json_file="$1"
    local pattern="$2"
    
    # Extract values matching pattern
    grep "$pattern" "$json_file" | sed 's/.*:[[:space:]]*"\?//' | sed 's/"\?,\?$//' 2>/dev/null
}#!/bin/bash

# Salesforce Test Coverage Query Script (READ-ONLY - NO TEST EXECUTION)
# Usage: ./query_coverage.sh [path_to_release_tests.txt]

set -e  # Exit on any error

# Configuration
TEST_FILE="${1:-release_tests.txt}"
OUTPUT_DIR="coverage_query_output"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Salesforce Coverage Query (READ-ONLY) ===${NC}"
echo "Timestamp: $(date)"
echo "Test file: $TEST_FILE"
echo -e "${GREEN}NOTE: This script only queries existing data - NO TESTS WILL BE RUN${NC}"
echo

# Check if test file exists
if [[ ! -f "$TEST_FILE" ]]; then
    echo -e "${RED}Error: Test file '$TEST_FILE' not found!${NC}"
    echo "Usage: $0 [path_to_release_tests.txt]"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Check SF CLI connection
echo -e "${BLUE}Checking Salesforce connection...${NC}"
if ! sf org display --json > /dev/null 2>&1; then
    echo -e "${RED}Error: Not connected to Salesforce org. Please run 'sf org login' first.${NC}"
    exit 1
fi

# Get current org info
ORG_INFO=$(sf org display --json)
ORG_ALIAS=$(echo "$ORG_INFO" | jq -r '.result.alias // .result.username')
ORG_TYPE=$(echo "$ORG_INFO" | jq -r '.result.instanceUrl // "Unknown"')
echo -e "${GREEN}Connected to: $ORG_ALIAS${NC}"
echo -e "${GREEN}Instance: $ORG_TYPE${NC}"
echo

# Read and process test classes
echo -e "${BLUE}Processing test classes from $TEST_FILE...${NC}"
if [[ ! -s "$TEST_FILE" ]]; then
    echo -e "${RED}Error: Test file is empty!${NC}"
    exit 1
fi

# Clean and prepare class list
TEST_CLASSES=($(cat "$TEST_FILE" | sed 's/[[:space:]]*$//' | sed '/^$/d'))
CLASS_COUNT=${#TEST_CLASSES[@]}

echo "Found $CLASS_COUNT test classes:"
printf '  - %s\n' "${TEST_CLASSES[@]}"
echo

# Create quoted class list for SOQL IN clause
create_class_list() {
    local classes=()
    for class in "${TEST_CLASSES[@]}"; do
        classes+=("'$class'")
    done
    echo $(IFS=','; echo "${classes[*]}")
}

CLASS_LIST=$(create_class_list)
SUMMARY_FILE="$OUTPUT_DIR/coverage_summary_${TIMESTAMP}.txt"

# Function to check what objects are available
check_available_objects() {
    echo -e "${BLUE}Checking what coverage objects are available...${NC}"
    
    local objects_file="$OUTPUT_DIR/available_objects_${TIMESTAMP}.json"
    
    # Check for coverage-related objects
    local coverage_query="SELECT QualifiedApiName, Label FROM EntityDefinition WHERE QualifiedApiName LIKE '%Coverage%' OR QualifiedApiName LIKE '%Test%'"
    
    if sf data query --query "$coverage_query" --use-tooling-api --json > "$objects_file" 2>&1; then
        echo -e "${GREEN}Available objects query succeeded${NC}"
        echo "Coverage/Test related objects found:"
        local count=$(count_json_records "$objects_file")
        echo "  Found $count objects (see $objects_file for details)"
    else
        echo -e "${YELLOW}Cannot query EntityDefinition (likely GovCloudPlus restriction)${NC}"
    fi
    echo
}

# Function to get class IDs for our test classes
get_class_ids() {
    echo -e "${BLUE}Getting Apex Class IDs for test classes...${NC}"
    
    local class_query="SELECT Id, Name FROM ApexClass WHERE Name IN ($CLASS_LIST)"
    local class_file="$OUTPUT_DIR/class_ids_${TIMESTAMP}.json"
    
    if sf data query --query "$class_query" --use-tooling-api --json > "$class_file" 2>&1; then
        echo -e "${GREEN}Successfully retrieved class information${NC}"
        
        local found_classes=$(count_json_records "$class_file")
        echo "Found $found_classes out of $CLASS_COUNT classes in the org"
        echo "Classes found in org:"
        extract_json_values "$class_file" '"Name"' | while read -r name; do
            if [[ -n "$name" ]]; then
                echo "  ✓ $name"
            fi
        done
        
        echo "Classes NOT found in org:"
        local found_names=($(extract_json_values "$class_file" '"Name"'))
        for test_class in "${TEST_CLASSES[@]}"; do
            if [[ ! " ${found_names[@]} " =~ " ${test_class} " ]]; then
                echo -e "  ${RED}✗ $test_class${NC}"
            fi
        done
        return 0
    else
        echo -e "${RED}Cannot query ApexClass object${NC}"
        cat "$class_file"
        return 1
    fi
    echo
}

# Function to try querying existing coverage data
query_existing_coverage() {
    echo -e "${BLUE}Attempting to query existing coverage data...${NC}"
    
    # List of coverage queries to try (from most specific to most general)
    local coverage_queries=(
        "SELECT Id, ApexClassOrTriggerId, NumLinesCovered, NumLinesUncovered, PercentCovered FROM ApexCodeCoverageAggregate LIMIT 10"
        "SELECT Id, ApexTestClassId, ApexClassOrTriggerId, NumLinesCovered, NumLinesUncovered FROM ApexCodeCoverage LIMIT 10"
        "SELECT Id, JobName, StartTime, EndTime, Status FROM ApexTestRunResult ORDER BY StartTime DESC LIMIT 5"
        "SELECT Id, ApexClassId, TestMethodName, Outcome FROM ApexTestResult ORDER BY SystemModstamp DESC LIMIT 10"
    )
    
    local success=false
    
    for i in "${!coverage_queries[@]}"; do
        local query="${coverage_queries[$i]}"
        local query_file="$OUTPUT_DIR/coverage_query_${i}_${TIMESTAMP}.json"
        
        echo "Trying coverage query $((i+1))..."
        if sf data query --query "$query" --use-tooling-api --json > "$query_file" 2>&1; then
            echo -e "${GREEN}Coverage query $((i+1)) succeeded!${NC}"
            
            local record_count=$(count_json_records "$query_file")
            echo "Found $record_count records"
            
            if [[ $record_count -gt 0 ]]; then
                echo "Sample data (first few fields):"
                head -20 "$query_file" | grep -E '"[A-Za-z]+":' | head -5 | sed 's/^[[:space:]]*/  /'
                success=true
            fi
            echo
        else
            echo -e "${YELLOW}Coverage query $((i+1)) failed${NC}"
            # Don't show error details to keep output clean
        fi
    done
    
    if [[ $success == false ]]; then
        echo -e "${RED}No coverage data queries succeeded${NC}"
        echo -e "${YELLOW}This likely means:${NC}"
        echo "  - You're in GovCloudPlus with restricted API access"
        echo "  - No tests have been run recently"
        echo "  - Coverage objects are not available in this org type"
    fi
}

# Function to get recent test run history (if available)
query_test_history() {
    echo -e "${BLUE}Checking recent test execution history...${NC}"
    
    local history_queries=(
        "SELECT Id, JobName, StartTime, EndTime, Status, UserId FROM ApexTestRunResult ORDER BY StartTime DESC LIMIT 10"
        "SELECT Id, ApexClassId, TestMethodName, Outcome, RunTime FROM ApexTestResult ORDER BY SystemModstamp DESC LIMIT 20"
    )
    
    for i in "${!history_queries[@]}"; do
        local query="${history_queries[$i]}"
        local history_file="$OUTPUT_DIR/test_history_${i}_${TIMESTAMP}.json"
        
        echo "Checking test history $((i+1))..."
        if sf data query --query "$query" --use-tooling-api --json > "$history_file" 2>&1; then
            echo -e "${GREEN}Test history query $((i+1)) succeeded!${NC}"
            
            local record_count=$(count_json_records "$history_file")
            if [[ $record_count -gt 0 ]]; then
                echo "Recent test activity found ($record_count records)"
                echo "Most recent (basic parsing):"
                head -20 "$history_file" | grep -E '"[A-Za-z]+":' | head -5 | sed 's/^[[:space:]]*/  /'
            else
                echo "No recent test activity found"
            fi
        else
            echo -e "${YELLOW}Test history query $((i+1)) failed${NC}"
        fi
    done
    echo
}

# Function to generate summary report
generate_summary() {
    echo -e "${BLUE}Generating summary report...${NC}"
    
    {
        echo "=== SALESFORCE COVERAGE QUERY SUMMARY ==="
        echo "Generated: $(date)"
        echo "Org: $ORG_ALIAS"
        echo "Instance: $ORG_TYPE"
        echo
        echo "=== TEST CLASSES ANALYZED ==="
        echo "Total classes in release_tests.txt: $CLASS_COUNT"
        printf '%s\n' "${TEST_CLASSES[@]}"
        echo
        echo "=== FINDINGS ==="
        echo "- This was a READ-ONLY query - no tests were executed"
        echo "- Check individual JSON files in $OUTPUT_DIR/ for detailed results"
        echo "- If no coverage data was found, it likely means:"
        echo "  * Tests haven't been run recently"
        echo "  * Coverage APIs are restricted (GovCloudPlus)"
        echo "  * Org doesn't have historical coverage data"
        echo
        echo "=== RECOMMENDATIONS ==="
        echo "To get current coverage data, you may need to:"
        echo "1. Run tests in a development environment"
        echo "2. Use 'sf project deploy validate' for safe coverage checking"
        echo "3. Work with your Salesforce admin for coverage access"
        echo
        echo "=== FILES GENERATED ==="
        ls -la "$OUTPUT_DIR/" | grep "$TIMESTAMP"
    } > "$SUMMARY_FILE"
    
    echo -e "${GREEN}Summary report saved to: $SUMMARY_FILE${NC}"
}

echo -e "${BLUE}Using built-in bash JSON parsing${NC}"

# Main execution
echo -e "${BLUE}=== STARTING READ-ONLY COVERAGE ANALYSIS ===${NC}"
echo -e "${GREEN}✓ No tests will be executed${NC}"
echo -e "${GREEN}✓ No objects will be created${NC}"
echo -e "${GREEN}✓ Only querying existing data${NC}"
echo

check_available_objects
get_class_ids
query_existing_coverage
query_test_history
generate_summary

echo
echo -e "${GREEN}=== ANALYSIS COMPLETE ===${NC}"
echo "All output files saved in: $OUTPUT_DIR/"
echo -e "${BLUE}View summary:${NC} cat $SUMMARY_FILE"
echo
echo -e "${YELLOW}Remember: This only shows existing coverage data.${NC}"
echo -e "${YELLOW}For current coverage, you'll need to run tests in a safe environment.${NC}"