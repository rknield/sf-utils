#!/usr/bin/env python3
"""
Simple Working Salesforce Code Coverage Checker
Requires Python 3.13.1 and SF CLI (not sfdx)

Usage: python sf_coverage_checker.py --org <org_alias> [options]
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import csv
import time
import concurrent.futures
import threading
from multiprocessing import cpu_count
import os
import platform
import shutil

class SFCLIDetector:
    """Smart SF CLI detection for cross-platform environments"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.sf_path = None
        self.is_windows = platform.system().lower() == 'windows'
        self.is_wsl = self._is_wsl()
    
    def _is_wsl(self) -> bool:
        """Detect if running in WSL"""
        try:
            with open('/proc/version', 'r') as f:
                return 'microsoft' in f.read().lower()
        except:
            return False
    
    def _log(self, message: str):
        """Internal logging"""
        if self.verbose:
            print(f"[SF-DETECT] {message}")
    
    def detect_sf_cli(self) -> Optional[str]:
        """Detect SF CLI installation across different environments"""
        self._log(f"Detecting SF CLI on {platform.system()} (WSL: {self.is_wsl})")
        
        # Try common command variations first
        simple_commands = ['sf', 'sfdx']
        for cmd in simple_commands:
            if self._test_command(cmd):
                self.sf_path = cmd
                self._log(f"Found SF CLI using simple command: {cmd}")
                return cmd
        
        # Try npx variations
        npx_commands = ['npx sf', 'npx @salesforce/cli', 'npx sfdx']
        for cmd in npx_commands:
            if self._test_command(cmd.split()):
                self.sf_path = cmd.split()
                self._log(f"Found SF CLI using npx: {cmd}")
                return cmd.split()
        
        # Search in common installation paths
        search_paths = self._get_search_paths()
        for path in search_paths:
            sf_executable = self._find_sf_in_path(path)
            if sf_executable and self._test_command([sf_executable]):
                self.sf_path = sf_executable
                self._log(f"Found SF CLI at: {sf_executable}")
                return sf_executable
        
        # Last resort: use 'which' or 'where' command
        location_cmd = 'where' if (self.is_windows and not self.is_wsl) else 'which'
        search_names = ['sf', 'sfdx']
        
        # Add Windows extensions when in PowerShell
        if self.is_windows and not self.is_wsl:
            search_names.extend(['sf.exe', 'sf.cmd', 'sf.bat', 'sfdx.exe', 'sfdx.cmd', 'sfdx.bat'])
        
        for sf_name in search_names:
            try:
                result = subprocess.run([location_cmd, sf_name], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0 and result.stdout.strip():
                    found_path = result.stdout.strip().split('\n')[0]
                    if self._test_command([found_path]):
                        self.sf_path = found_path
                        self._log(f"Found SF CLI using {location_cmd}: {found_path}")
                        return found_path
            except:
                continue
        
        self._log("SF CLI not found in any common locations")
        return None
    
    def _get_search_paths(self) -> List[str]:
        """Get platform-specific search paths"""
        paths = []
        
        if self.is_windows:
            # Windows paths
            program_files = [
                os.environ.get('PROGRAMFILES', 'C:\\Program Files'),
                os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)'),
                os.environ.get('LOCALAPPDATA', ''),
                os.environ.get('APPDATA', '')
            ]
            
            for pf in program_files:
                if pf:
                    paths.extend([
                        os.path.join(pf, 'Salesforce CLI'),
                        os.path.join(pf, 'sfdx'),
                        os.path.join(pf, 'sf'),
                        os.path.join(pf, 'nodejs'),
                        os.path.join(pf, 'npm', 'node_modules', '.bin'),
                        os.path.join(pf, 'npm', 'node_modules', '@salesforce', 'cli', 'bin')
                    ])
            
            # User-specific paths
            userprofile = os.environ.get('USERPROFILE', '')
            if userprofile:
                paths.extend([
                    os.path.join(userprofile, 'AppData', 'Roaming', 'npm'),
                    os.path.join(userprofile, 'AppData', 'Roaming', 'npm', 'node_modules', '.bin'),
                    os.path.join(userprofile, '.npm-global', 'bin'),
                    os.path.join(userprofile, 'scoop', 'apps', 'salesforce-cli'),
                    os.path.join(userprofile, 'scoop', 'shims')
                ])
        
        else:
            # Unix-like paths (Linux, macOS, WSL)
            home = os.path.expanduser('~')
            paths.extend([
                '/usr/local/bin',
                '/usr/bin',
                '/bin',
                '/opt/sf/bin',
                '/opt/salesforce/bin',
                os.path.join(home, '.local', 'bin'),
                os.path.join(home, '.npm-global', 'bin'),
                os.path.join(home, 'node_modules', '.bin'),
                '/usr/local/lib/node_modules/.bin',
                '/usr/lib/node_modules/.bin'
            ])
            
            # Check npm config prefix (corporate-friendly approach)
            try:
                result = subprocess.run(['npm', 'config', 'get', 'prefix'], 
                                      capture_output=True, text=True, timeout=15)
                if result.returncode == 0 and result.stdout.strip():
                    npm_prefix = result.stdout.strip()
                    self._log(f"NPM prefix: {npm_prefix}")
                    # Add common paths under the prefix
                    prefix_paths = [
                        npm_prefix,
                        os.path.join(npm_prefix, 'bin'),
                        os.path.join(npm_prefix, 'node_modules', '.bin'),
                        os.path.join(npm_prefix, 'lib', 'node_modules', '.bin')
                    ]
                    paths.extend(prefix_paths)
            except Exception as e:
                self._log(f"Could not get npm prefix: {e}")
                pass
        
        # Try to get npm prefix for corporate environments
        self._add_npm_prefix_paths(paths)
        
        # Remove duplicates and non-existent paths
        unique_paths = []
        for path in paths:
            if path and os.path.exists(path) and path not in unique_paths:
                unique_paths.append(path)
        
        self._log(f"Searching in {len(unique_paths)} potential paths")
        if self.verbose:
            for i, path in enumerate(unique_paths[:10]):  # Show first 10 paths
                self._log(f"  {i+1}. {path}")
            if len(unique_paths) > 10:
                self._log(f"  ... and {len(unique_paths) - 10} more paths")
        
        return unique_paths
    
    def _add_npm_prefix_paths(self, paths: List[str]):
        """Add paths based on npm config prefix only (corporate-friendly)"""
        self._log("Checking npm prefix for SF CLI installation...")
        
        try:
            # Only use npm config get prefix - safe for corporate environments
            result = subprocess.run(['npm', 'config', 'get', 'prefix'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                npm_prefix = result.stdout.strip()
                self._log(f"Found npm prefix: {npm_prefix}")
                
                # Build potential SF CLI paths from the prefix
                prefix_paths = [
                    # Direct bin directory
                    os.path.join(npm_prefix, 'bin'),
                    
                    # Node modules bin directories  
                    os.path.join(npm_prefix, 'node_modules', '.bin'),
                    os.path.join(npm_prefix, 'lib', 'node_modules', '.bin'),
                    
                    # Specific SF CLI installation paths
                    os.path.join(npm_prefix, 'node_modules', '@salesforce', 'cli', 'bin'),
                    os.path.join(npm_prefix, 'lib', 'node_modules', '@salesforce', 'cli', 'bin'),
                    os.path.join(npm_prefix, 'node_modules', 'sfdx', 'bin'),
                    os.path.join(npm_prefix, 'lib', 'node_modules', 'sfdx', 'bin'),
                    
                    # The prefix itself
                    npm_prefix
                ]
                
                self._log(f"Adding {len(prefix_paths)} npm-prefix-based paths")
                paths.extend(prefix_paths)
                
        except Exception as e:
            self._log(f"Could not get npm prefix: {e}")
            pass
    
    def _find_sf_in_path(self, search_path: str) -> Optional[str]:
        """Find SF CLI executable in a specific path"""
        if not os.path.exists(search_path):
            return None
        
        # Different executable names for different environments
        if self.is_windows and not self.is_wsl:
            # PowerShell/Windows: need .exe, .cmd, .bat extensions
            sf_names = ['sf.exe', 'sf.cmd', 'sf.bat', 'sf', 'sfdx.exe', 'sfdx.cmd', 'sfdx.bat', 'sfdx']
        else:
            # WSL/Linux/macOS: no extensions needed
            sf_names = ['sf', 'sfdx']
        
        self._log(f"Searching for {sf_names} in {search_path}")
        
        for sf_name in sf_names:
            sf_full_path = os.path.join(search_path, sf_name)
            if os.path.isfile(sf_full_path):
                # Additional check: ensure it's executable
                if self._is_executable(sf_full_path):
                    self._log(f"Found executable SF CLI: {sf_full_path}")
                    return sf_full_path
                else:
                    self._log(f"Found {sf_full_path} but it's not executable")
        
        return None
    
    def _is_executable(self, file_path: str) -> bool:
        """Check if a file is executable"""
        if not os.path.isfile(file_path):
            return False
        
        if self.is_windows and not self.is_wsl:
            # On Windows, check file extension
            _, ext = os.path.splitext(file_path.lower())
            return ext in ['.exe', '.cmd', '.bat', '.com'] or os.access(file_path, os.X_OK)
        else:
            # On Unix-like systems (including WSL), check execute permission
            return os.access(file_path, os.X_OK)
    
    def _test_command(self, cmd) -> bool:
        """Test if a command works"""
        try:
            # Ensure cmd is a list
            if isinstance(cmd, str):
                cmd = [cmd]
            
            # Test with --version flag
            test_cmd = cmd + ['--version']
            result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=10)
            
            success = result.returncode == 0 and 'salesforce' in result.stdout.lower()
            if success:
                self._log(f"Successfully tested command: {' '.join(cmd)}")
            else:
                self._log(f"Command test failed for: {' '.join(cmd)} (returncode: {result.returncode})")
                
            return success
        except Exception as e:
            self._log(f"Exception testing command {cmd}: {e}")
            return False
    
    def get_sf_command(self) -> List[str]:
        """Get the SF CLI command as a list for subprocess"""
        if self.sf_path is None:
            self.detect_sf_cli()
        
        if self.sf_path is None:
            return None
        
        if isinstance(self.sf_path, list):
            return self.sf_path
        else:
            return [self.sf_path]

class SalesforceCodeCoverage:
    def __init__(self, org_alias: str, verbose: bool = False, max_workers: int = None):
        self.org_alias = org_alias
        self.verbose = verbose
        self.max_workers = max_workers or min(4, cpu_count())
        self.coverage_data = {}
        self.test_results = {}
        self.org_info = {}
        self._lock = threading.Lock()
        
        # Initialize SF CLI detector
        self.sf_detector = SFCLIDetector(verbose)
        self.sf_command = None
        
    def _ensure_sf_cli(self) -> bool:
        """Ensure SF CLI is available and detected"""
        if self.sf_command is None:
            self.log("Detecting SF CLI installation...")
            self.sf_command = self.sf_detector.get_sf_command()
            
            if self.sf_command is None:
                self.log("SF CLI not found. Please install SF CLI:", "ERROR")
                self.log("  Option 1: Download from https://developer.salesforce.com/tools/salesforcecli", "ERROR")
                self.log("  Option 2: Install via npm: npm install -g @salesforce/cli", "ERROR")
                self.log("  Option 3: Use package manager (choco, brew, apt, etc.)", "ERROR")
                return False
            
            # Test the detected command
            cmd_str = ' '.join(self.sf_command) if isinstance(self.sf_command, list) else self.sf_command
            self.log(f"Using SF CLI: {cmd_str}")
            
        return True
        
    def log(self, message: str, level: str = "INFO"):
        """Thread-safe logging with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self.verbose or level in ["ERROR", "WARNING"]:
            with self._lock:
                print(f"[{timestamp}] {level}: {message}")
    
    def run_sf_command(self, sf_args: List[str]) -> Tuple[bool, str, str]:
        """Execute SF CLI command and return success status, stdout, stderr"""
        if not self._ensure_sf_cli():
            return False, "", "SF CLI not available"
        
        try:
            # Build complete command
            command = self.sf_command + sf_args
            
            self.log(f"Running: {' '.join(command)}")
            result = subprocess.run(
                command, 
                capture_output=True, 
                text=True, 
                timeout=300
            )
            
            if result.returncode != 0 and self.verbose:
                self.log(f"Command failed: {result.stderr}", "DEBUG")
            
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            self.log("Command timed out after 5 minutes", "ERROR")
            return False, "", "Command timeout"
        except Exception as e:
            self.log(f"Command execution failed: {str(e)}", "ERROR")
            return False, "", str(e)
    
    def verify_org_connection(self) -> bool:
        """Verify SF CLI is installed and org is authenticated"""
        self.log("Verifying SF CLI installation and org authentication...")
        
        # Check SF CLI installation
        success, stdout, stderr = self.run_sf_command(["--version"])
        if not success:
            return False
        
        self.log(f"SF CLI version: {stdout.strip()}")
        
        # Check org authentication and get org details
        success, stdout, stderr = self.run_sf_command([
            "org", "display", "--target-org", self.org_alias, "--json"
        ])
        
        if not success:
            self.log(f"Failed to connect to org '{self.org_alias}'. Please check authentication.", "ERROR")
            self.log(f"Try: {' '.join(self.sf_command)} org login web --alias {self.org_alias}", "ERROR")
            return False
        
        try:
            org_info = json.loads(stdout)
            result = org_info.get("result", {})
            
            self.org_info = {
                "org_name": result.get("alias", result.get("username", "Unknown")),
                "org_url": result.get("instanceUrl", "Unknown"),
                "username": result.get("username", "Unknown"),
                "org_id": result.get("id", "Unknown")
            }
            
            self.log(f"Connected to org: {self.org_info['username']}")
            return True
        except json.JSONDecodeError:
            self.log("Failed to parse org information", "ERROR")
            return False
    
    def get_apex_classes(self) -> List[Dict]:
        """Retrieve all Apex classes from the org"""
        self.log("Retrieving Apex classes...")
        
        query = "SELECT Id, Name FROM ApexClass WHERE NamespacePrefix = null ORDER BY Name"
        success, stdout, stderr = self.run_sf_command([
            "data", "query", "--query", query, 
            "--target-org", self.org_alias, "--json"
        ])
        
        if not success:
            self.log(f"Failed to query Apex classes: {stderr}", "ERROR")
            return []
        
        try:
            result = json.loads(stdout)
            classes = result.get("result", {}).get("records", [])
            self.log(f"Found {len(classes)} Apex classes")
            return classes
        except json.JSONDecodeError:
            self.log("Failed to parse Apex classes query result", "ERROR")
            return []
    
    def get_apex_triggers(self) -> List[Dict]:
        """Retrieve all Apex triggers from the org"""
        self.log("Retrieving Apex triggers...")
        
        query = "SELECT Id, Name FROM ApexTrigger WHERE NamespacePrefix = null ORDER BY Name"
        success, stdout, stderr = self.run_sf_command([
            "data", "query", "--query", query, 
            "--target-org", self.org_alias, "--json"
        ])
        
        if not success:
            self.log(f"Failed to query Apex triggers: {stderr}", "ERROR")
            return []
        
        try:
            result = json.loads(stdout)
            triggers = result.get("result", {}).get("records", [])
            self.log(f"Found {len(triggers)} Apex triggers")
            return triggers
        except json.JSONDecodeError:
            self.log("Failed to parse Apex triggers query result", "ERROR")
            return []
    
    def run_all_tests(self) -> bool:
        """Run all tests in the org"""
        self.log("Running all tests in the organization...")
        
        success, stdout, stderr = self.run_sf_command([
            "apex", "run", "test", "--test-level", "RunLocalTests",
            "--target-org", self.org_alias, "--wait", "30", "--json"
        ])
        
        if not success:
            self.log(f"Test run failed: {stderr}", "ERROR")
            return False
        
        try:
            result = json.loads(stdout)
            test_result = result.get("result", {})
            
            self.test_results = {
                "summary": test_result.get("summary", {}),
                "tests": test_result.get("tests", []),
                "codecoverage": test_result.get("codecoverage", [])
            }
            
            summary = self.test_results["summary"]
            self.log(f"Test run completed:")
            self.log(f"  - Total tests: {summary.get('testsRan', 0)}")
            self.log(f"  - Passed: {summary.get('passing', 0)}")
            self.log(f"  - Failed: {summary.get('failing', 0)}")
            
            coverage_pct = float(summary.get('testRunCoverage', '0'))
            self.log(f"  - Overall coverage: {coverage_pct:.2f}%")
            
            return True
            
        except json.JSONDecodeError:
            self.log("Failed to parse test results", "ERROR")
            return False
    
    def get_coverage_data_parallel(self) -> Dict:
        """Get coverage data using parallel queries"""
        self.log("Retrieving coverage data...")
        
        queries = {
            "aggregate": """
                SELECT ApexClassOrTrigger.Name, ApexClassOrTrigger.Id, 
                       NumLinesCovered, NumLinesUncovered
                FROM ApexCodeCoverageAggregate 
                WHERE ApexClassOrTrigger.NamespacePrefix = null
                ORDER BY ApexClassOrTrigger.Name
            """,
            "test_results": """
                SELECT ApexClass.Name, MethodName, Outcome, 
                       RunTime, Message, StackTrace
                FROM ApexTestResult 
                ORDER BY ApexClass.Name, MethodName
            """,
            "test_coverage": """
                SELECT ApexTestClass.Name, TestMethodName,
                       SUM(NumLinesCovered) CoveredLines,
                       SUM(NumLinesUncovered) UncoveredLines
                FROM ApexCodeCoverage 
                WHERE ApexTestClass.NamespacePrefix = null
                GROUP BY ApexTestClass.Name, TestMethodName
                ORDER BY ApexTestClass.Name, TestMethodName
            """
        }
        
        def execute_query(query_info):
            query_type, query = query_info
            success, stdout, stderr = self.run_sf_command([
                "data", "query", "--query", query,
                "--target-org", self.org_alias, "--json"
            ])
            
            if not success:
                self.log(f"Failed to execute {query_type} query: {stderr}", "WARNING")
                return query_type, []
            
            try:
                result = json.loads(stdout)
                records = result.get("result", {}).get("records", [])
                self.log(f"Retrieved {len(records)} records for {query_type}")
                return query_type, records
            except json.JSONDecodeError:
                self.log(f"Failed to parse {query_type} query result", "ERROR")
                return query_type, []
        
        # Execute queries in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(execute_query, item) for item in queries.items()]
            results = {}
            
            for future in concurrent.futures.as_completed(futures):
                query_type, records = future.result()
                results[query_type] = records
        
        return results
    
    def process_coverage_data(self, aggregate_records: List[Dict]) -> Dict:
        """Process aggregate coverage data"""
        if not aggregate_records:
            return {}
        
        coverage_data = {}
        for record in aggregate_records:
            name = record.get("ApexClassOrTrigger", {}).get("Name")
            if name:
                covered = record.get("NumLinesCovered", 0) or 0
                uncovered = record.get("NumLinesUncovered", 0) or 0
                total = covered + uncovered
                
                coverage_data[name] = {
                    "id": record.get("ApexClassOrTrigger", {}).get("Id"),
                    "covered_lines": covered,
                    "uncovered_lines": uncovered,
                    "total_lines": total,
                    "coverage_percentage": round((covered / total * 100), 2) if total > 0 else 0.00
                }
        
        self.log(f"Processed coverage data for {len(coverage_data)} items")
        return coverage_data
    
    def process_test_results(self, test_records: List[Dict], test_coverage_records: List[Dict]) -> Dict:
        """Process test results with coverage"""
        if not test_records:
            return {}
        
        # Create coverage lookup
        coverage_lookup = {}
        for record in test_coverage_records:
            test_class = record.get("ApexTestClass", {}).get("Name")
            test_method = record.get("TestMethodName")
            if test_class and test_method:
                key = f"{test_class}.{test_method}"
                covered = record.get("CoveredLines", 0) or 0
                uncovered = record.get("UncoveredLines", 0) or 0
                total = covered + uncovered
                
                coverage_lookup[key] = {
                    "covered_lines": covered,
                    "uncovered_lines": uncovered,
                    "total_lines": total,
                    "coverage_percentage": round((covered / total * 100), 2) if total > 0 else 0.00
                }
        
        # Process test results
        detailed_tests = {}
        for test in test_records:
            class_name = test.get("ApexClass", {}).get("Name", "Unknown")
            method_name = test.get("MethodName", "Unknown")
            test_key = f"{class_name}.{method_name}"
            
            coverage_info = coverage_lookup.get(test_key, {
                "covered_lines": 0,
                "uncovered_lines": 0,
                "total_lines": 0,
                "coverage_percentage": 0.00
            })
            
            detailed_tests[test_key] = {
                "class_name": class_name,
                "method_name": method_name,
                "outcome": test.get("Outcome", "Unknown"),
                "runtime": test.get("RunTime", 0),
                "message": test.get("Message", ""),
                **coverage_info
            }
        
        self.log(f"Processed {len(detailed_tests)} test results")
        return detailed_tests
    
    def analyze_coverage_gaps(self, coverage_data: Dict, classes: List[Dict], triggers: List[Dict]) -> Dict:
        """Analyze coverage gaps"""
        self.log("Analyzing coverage gaps...")
        
        all_apex_items = {item["Name"]: {"type": "class", "id": item["Id"]} for item in classes}
        all_apex_items.update({item["Name"]: {"type": "trigger", "id": item["Id"]} for item in triggers})
        
        analysis = {
            "total_classes_triggers": len(all_apex_items),
            "tested_items": len(coverage_data),
            "untested_items": [],
            "low_coverage_items": [],
            "no_coverage_items": [],
            "good_coverage_items": [],
            "overall_stats": {
                "total_lines": 0,
                "covered_lines": 0,
                "uncovered_lines": 0
            }
        }
        
        # Find untested items
        for name, info in all_apex_items.items():
            if name not in coverage_data:
                analysis["untested_items"].append({
                    "name": name,
                    "type": info["type"],
                    "id": info["id"]
                })
        
        # Categorize by coverage
        total_lines = 0
        total_covered = 0
        
        for name, data in coverage_data.items():
            coverage_pct = data["coverage_percentage"]
            total_lines += data["total_lines"]
            total_covered += data["covered_lines"]
            
            item_info = {
                "name": name,
                "coverage_percentage": coverage_pct,
                "covered_lines": data["covered_lines"],
                "total_lines": data["total_lines"]
            }
            
            if coverage_pct == 0:
                analysis["no_coverage_items"].append(item_info)
            elif coverage_pct < 75:
                analysis["low_coverage_items"].append(item_info)
            else:
                analysis["good_coverage_items"].append(item_info)
        
        analysis["overall_stats"]["total_lines"] = total_lines
        analysis["overall_stats"]["covered_lines"] = total_covered
        analysis["overall_stats"]["uncovered_lines"] = total_lines - total_covered
        analysis["overall_stats"]["coverage_percentage"] = round((total_covered / total_lines * 100), 2) if total_lines > 0 else 0.00
        
        return analysis
    
    def generate_report(self, coverage_data: Dict, analysis: Dict, detailed_tests: Dict, output_file: Optional[str] = None):
        """Generate comprehensive coverage report"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Get org information
        org_name = self.org_info.get("org_name", "Unknown")
        org_url = self.org_info.get("org_url", "Unknown")
        
        report_lines = [
            "=" * 80,
            f"SALESFORCE CODE COVERAGE REPORT",
            f"Generated: {timestamp}",
            "=" * 80,
            "",
            f"**{org_name}**",
            f"Org Url: {org_url}",
            f"Covered Lines: {analysis['overall_stats']['covered_lines']:,}",
            f"Uncovered Lines: {analysis['overall_stats']['uncovered_lines']:,}",
            f"Total Coverage for Org: {analysis['overall_stats']['coverage_percentage']:.2f}%",
            "",
            "=" * 80,
            ""
        ]
        
        # Test execution summary
        if self.test_results and "summary" in self.test_results:
            summary = self.test_results["summary"]
            test_run_coverage = float(summary.get('testRunCoverage', '0'))
            report_lines.extend([
                "TEST EXECUTION SUMMARY:",
                f"  Tests Run: {summary.get('testsRan', 0):,}",
                f"  Tests Passed: {summary.get('passing', 0):,}",
                f"  Tests Failed: {summary.get('failing', 0):,}",
                f"  Test Run Coverage: {test_run_coverage:.2f}%",
                f"  Execution Time: {summary.get('testExecutionTimeInMs', 0):,}ms",
                ""
            ])
        
        # Individual test results with coverage
        if detailed_tests:
            report_lines.extend([
                "INDIVIDUAL TEST COVERAGE:",
                "-" * 80
            ])
            
            sorted_tests = sorted(detailed_tests.items(), key=lambda x: (x[1]['class_name'], x[1]['method_name']))
            
            for test_key, test_info in sorted_tests:
                test_name = f"{test_info['class_name']}.{test_info['method_name']}"
                covered = test_info['covered_lines']
                uncovered = test_info['uncovered_lines']
                coverage_pct = test_info['coverage_percentage']
                outcome = test_info['outcome']
                
                status_indicator = "PASS" if outcome == "Pass" else "FAIL"
                
                report_lines.append(
                    f"{status_indicator:<4} {test_name:<50} "
                    f"Covered: {covered:>4} | Uncovered: {uncovered:>4} | Coverage: {coverage_pct:>6.2f}%"
                )
                
                if outcome != "Pass" and test_info.get('message'):
                    report_lines.append(f"     Error: {test_info['message']}")
            
            report_lines.append("")
        elif self.test_results and "tests" in self.test_results:
            # Fallback: show basic test results without detailed coverage
            report_lines.extend([
                "TEST RESULTS (No detailed coverage available):",
                "-" * 80
            ])
            
            for test in self.test_results["tests"]:
                class_name = test.get("ApexClass", {}).get("Name", "Unknown")
                method_name = test.get("MethodName", "Unknown")
                outcome = test.get("Outcome", "Unknown")
                
                status_indicator = "PASS" if outcome == "Pass" else "FAIL"
                test_name = f"{class_name}.{method_name}"
                
                report_lines.append(f"{status_indicator:<4} {test_name}")
                
                if outcome != "Pass" and test.get("Message"):
                    report_lines.append(f"     Error: {test['Message']}")
            
            report_lines.append("")
        
        # Coverage breakdown
        report_lines.extend([
            "COVERAGE BREAKDOWN:",
            f"  Good Coverage (≥75%): {len(analysis['good_coverage_items']):,} items",
            f"  Low Coverage (<75%): {len(analysis['low_coverage_items']):,} items",
            f"  No Coverage (0%): {len(analysis['no_coverage_items']):,} items",
            f"  Completely Untested: {len(analysis['untested_items']):,} items",
            ""
        ])
        
        # Detailed coverage for each item
        if coverage_data:
            # Only show items that have actual coverage data (not just placeholders)
            items_with_coverage = {name: data for name, data in coverage_data.items() if data['total_lines'] > 0}
            
            if items_with_coverage:
                report_lines.extend([
                    "DETAILED COVERAGE BY CLASS/TRIGGER:",
                    "-" * 80
                ])
                
                sorted_items = sorted(items_with_coverage.items(), key=lambda x: x[1]['coverage_percentage'])
                
                for name, data in sorted_items:
                    report_lines.append(
                        f"{name:<40} {data['coverage_percentage']:>7.2f}% "
                        f"({data['covered_lines']:>4,}/{data['total_lines']:<4,} lines)"
                    )
            else:
                report_lines.extend([
                    "",
                    "NO DETAILED COVERAGE DATA AVAILABLE",
                    "Run tests first to generate coverage data:",
                    "  sf apex run test --test-level RunLocalTests --target-org " + self.org_alias,
                    ""
                ])
        
        # Items needing attention
        sections = [
            ("untested_items", "UNTESTED CLASSES/TRIGGERS:", lambda item: f"  {item['name']} ({item['type']})"),
            ("no_coverage_items", "ITEMS WITH 0% COVERAGE:", lambda item: f"  {item['name']} - {item['total_lines']:,} lines"),
            ("low_coverage_items", "ITEMS WITH LOW COVERAGE (<75%):", 
             lambda item: f"  {item['name']:<35} {item['coverage_percentage']:>7.2f}% ({item['covered_lines']:,}/{item['total_lines']:,} lines)")
        ]
        
        for section_key, title, formatter in sections:
            items = analysis[section_key]
            if items:
                report_lines.extend(["", title, "-" * 40])
                
                if section_key == "low_coverage_items":
                    items = sorted(items, key=lambda x: x['coverage_percentage'])
                
                for item in items:
                    report_lines.append(formatter(item))
        
        # Failed tests summary
        if detailed_tests:
            failed_tests = [t for t in detailed_tests.values() if t.get('outcome') != 'Pass']
            if failed_tests:
                report_lines.extend([
                    "",
                    "FAILED TESTS SUMMARY:",
                    "-" * 40
                ])
                for test in failed_tests:
                    test_name = f"{test['class_name']}.{test['method_name']}"
                    report_lines.append(f"  {test_name}")
                    if test.get('message'):
                        report_lines.append(f"    Error: {test['message']}")
        
        report_text = "\n".join(report_lines)
        
        # Output
        if output_file:
            try:
                with open(output_file, 'w') as f:
                    f.write(report_text)
                self.log(f"Report saved to {output_file}")
            except Exception as e:
                self.log(f"Failed to save report to file: {e}", "ERROR")
                print(report_text)
        else:
            print(report_text)
    
    def export_to_csv(self, coverage_data: Dict, filename: str):
        """Export coverage data to CSV"""
        try:
            with open(filename, 'w', newline='') as csvfile:
                fieldnames = ['Name', 'Coverage_Percentage', 'Covered_Lines', 'Total_Lines', 'Uncovered_Lines']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for name, data in sorted(coverage_data.items()):
                    writer.writerow({
                        'Name': name,
                        'Coverage_Percentage': f"{data['coverage_percentage']:.2f}",
                        'Covered_Lines': data['covered_lines'],
                        'Total_Lines': data['total_lines'],
                        'Uncovered_Lines': data['uncovered_lines']
                    })
            
            self.log(f"Coverage data exported to {filename}")
        except Exception as e:
            self.log(f"Failed to export CSV: {e}", "ERROR")
    
    def run_comprehensive_check(self, run_tests: bool = True, output_file: Optional[str] = None, csv_export: Optional[str] = None) -> bool:
        """Run comprehensive code coverage check"""
        start_time = time.time()
        self.log("Starting comprehensive code coverage check...")
        self.log(f"Using {self.max_workers} worker threads")
        
        # Step 1: Verify connection
        if not self.verify_org_connection():
            return False
        
        # Step 2: Get Apex classes and triggers in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            class_future = executor.submit(self.get_apex_classes)
            trigger_future = executor.submit(self.get_apex_triggers)
            
            classes = class_future.result()
            triggers = trigger_future.result()
        
        if not classes and not triggers:
            self.log("No Apex classes or triggers found", "WARNING")
            return False
        
        # Step 3: Run tests if requested
        if run_tests:
            if not self.run_all_tests():
                self.log("Test execution failed, but continuing with existing coverage data", "WARNING")
        
        # Step 4: Get coverage data in parallel
        coverage_results = self.get_coverage_data_parallel()
        
        aggregate_records = coverage_results.get("aggregate", [])
        test_records = coverage_results.get("test_results", [])
        test_coverage_records = coverage_results.get("test_coverage", [])
        
        if not aggregate_records and not test_records:
            self.log("No coverage data found. Try running tests first.", "ERROR")
            return False
        
        # Step 5: Process data
        coverage_data = self.process_coverage_data(aggregate_records)
        detailed_tests = self.process_test_results(test_records, test_coverage_records)
        
        # If no aggregate coverage but have test results, build from tests
        if not coverage_data and detailed_tests:
            self.log("Building coverage from test results...")
            coverage_data = {}
            for test_key, test_info in detailed_tests.items():
                class_name = test_info['class_name']
                # Include ALL test classes, even with 0 coverage
                if class_name not in coverage_data:
                    coverage_data[class_name] = {
                        "id": "unknown",
                        "covered_lines": test_info['covered_lines'],
                        "uncovered_lines": test_info['uncovered_lines'], 
                        "total_lines": test_info['total_lines'],
                        "coverage_percentage": test_info['coverage_percentage']
                    }
                else:
                    # Aggregate if multiple tests for same class
                    existing = coverage_data[class_name]
                    total_covered = existing["covered_lines"] + test_info['covered_lines']
                    total_uncovered = existing["uncovered_lines"] + test_info['uncovered_lines']
                    total_lines = total_covered + total_uncovered
                    
                    coverage_data[class_name].update({
                        "covered_lines": total_covered,
                        "uncovered_lines": total_uncovered,
                        "total_lines": total_lines,
                        "coverage_percentage": round((total_covered / total_lines * 100), 2) if total_lines > 0 else 0.00
                    })
            
            self.log(f"Built coverage data for {len(coverage_data)} classes from test results")
        
        # If still no meaningful coverage data, create placeholders but continue
        if not coverage_data:
            self.log("Creating placeholder coverage data for all classes/triggers...")
            coverage_data = {}
            
            # Add all classes/triggers with 0 coverage as placeholder
            for cls in classes:
                coverage_data[cls["Name"]] = {
                    "id": cls["Id"],
                    "covered_lines": 0,
                    "uncovered_lines": 0,
                    "total_lines": 0,
                    "coverage_percentage": 0.00
                }
            
            for trigger in triggers:
                coverage_data[trigger["Name"]] = {
                    "id": trigger["Id"],
                    "covered_lines": 0,
                    "uncovered_lines": 0,
                    "total_lines": 0,
                    "coverage_percentage": 0.00
                }
        
        # Always continue - we have data to work with
        self.log(f"Proceeding with analysis for {len(coverage_data)} items")
        
        # Step 6: Analyze coverage gaps
        analysis = self.analyze_coverage_gaps(coverage_data, classes, triggers)
        
        # Step 7: Generate report
        self.generate_report(coverage_data, analysis, detailed_tests, output_file)
        
        # Step 8: Export CSV if requested
        if csv_export:
            self.export_to_csv(coverage_data, csv_export)
        
        # Performance summary
        total_time = time.time() - start_time
        self.log(f"Coverage check completed in {total_time:.2f} seconds")
        
        return True

def main():
    parser = argparse.ArgumentParser(
        description="Salesforce Code Coverage Checker with Multithreading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python sf_coverage_checker.py --org myorg
  python sf_coverage_checker.py --org myorg --no-tests --output report.txt
  python sf_coverage_checker.py --org myorg --csv coverage.csv --verbose --workers 8
        """
    )
    
    parser.add_argument("--org", required=True, help="Salesforce org alias or username")
    parser.add_argument("--no-tests", action="store_true", help="Skip running tests, use existing coverage data")
    parser.add_argument("--output", help="Output file for the report")
    parser.add_argument("--csv", help="Export coverage data to CSV file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    parser.add_argument("--workers", type=int, default=0, help="Number of worker threads (default: auto)")
    
    args = parser.parse_args()
    
    # Determine worker count
    max_workers = args.workers if args.workers > 0 else min(4, cpu_count())
    
    checker = SalesforceCodeCoverage(args.org, args.verbose, max_workers)
    
    try:
        success = checker.run_comprehensive_check(
            run_tests=not args.no_tests,
            output_file=args.output,
            csv_export=args.csv
        )
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()