/**
 * Salesforce Service
 * Handles all Salesforce CLI interactions
 */

const { spawn } = require('child_process');
const os = require('os');
const path = require('path');
const fs = require('fs');

class SalesforceService {
    constructor(config) {
        this.config = config;
        this.sfCommand = null;
    }

    async initialize() {
        console.log('🔍 Detecting SF CLI...');
        this.sfCommand = await this.findSFCLI();
        if (!this.sfCommand) {
            throw new Error('SF CLI not found. Please install SF CLI.');
        }
        console.log(`✅ Found SF CLI: ${this.sfCommand.join(' ')}`);
    }

    async findSFCLI() {
        // Try simple commands first
        const simpleCommands = ['sf', 'npx sf'];
        
        for (const cmd of simpleCommands) {
            try {
                const result = await this.runCommand(cmd.split(' ').concat(['--version']));
                if (result.success && result.stdout.toLowerCase().includes('salesforce')) {
                    return cmd.split(' ');
                }
            } catch (e) {
                continue;
            }
        }

        // Try npm prefix method
        try {
            const npmResult = await this.runCommand(['npm', 'config', 'get', 'prefix']);
            if (npmResult.success) {
                const npmPrefix = npmResult.stdout.trim();
                const isWindows = os.platform() === 'win32';
                const sfFile = isWindows ? 'sf.cmd' : 'sf';
                
                const possiblePaths = [
                    path.join(npmPrefix, 'node_modules', '.bin', sfFile),
                    path.join(npmPrefix, 'bin', sfFile)
                ];

                for (const sfPath of possiblePaths) {
                    if (fs.existsSync(sfPath)) {
                        try {
                            const testResult = await this.runCommand([sfPath, '--version']);
                            if (testResult.success) {
                                return [sfPath];
                            }
                        } catch (e) {
                            continue;
                        }
                    }
                }
            }
        } catch (e) {
            // npm not available, continue
        }

        return null;
    }

    runCommand(args, options = {}) {
        return new Promise((resolve) => {
            const child = spawn(args[0], args.slice(1), {
                stdio: 'pipe',
                timeout: options.timeout || this.config.commandTimeout,
                ...options
            });

            let stdout = '';
            let stderr = '';

            child.stdout?.on('data', (data) => {
                stdout += data.toString();
            });

            child.stderr?.on('data', (data) => {
                stderr += data.toString();
            });

            child.on('close', (code) => {
                resolve({
                    success: code === 0,
                    stdout: stdout.trim(),
                    stderr: stderr.trim(),
                    code
                });
            });

            child.on('error', (err) => {
                resolve({
                    success: false,
                    stdout: '',
                    stderr: err.message,
                    code: -1
                });
            });
        });
    }

    async runSFCommand(args) {
        const fullArgs = [...this.sfCommand, ...args];
        return await this.runCommand(fullArgs);
    }

    async getAvailableOrgs() {
        const result = await this.runSFCommand(['org', 'list', '--json']);
        
        if (!result.success) {
            return [];
        }

        try {
            const data = JSON.parse(result.stdout);
            const orgs = [];

            // Non-scratch orgs
            const nonScratch = data.result?.nonScratchOrgs || [];
            nonScratch.forEach(org => {
                orgs.push({
                    alias: org.alias || '',
                    username: org.username || '',
                    type: 'Production/Sandbox',
                    identifier: org.alias || org.username
                });
            });

            // Scratch orgs
            const scratch = data.result?.scratchOrgs || [];
            scratch.forEach(org => {
                orgs.push({
                    alias: org.alias || '',
                    username: org.username || '',
                    type: 'Scratch Org',
                    identifier: org.alias || org.username
                });
            });

            return orgs;
        } catch (e) {
            console.error('Failed to parse org list:', e.message);
            return [];
        }
    }

    async getOrgInfo(orgAlias) {
        const result = await this.runSFCommand(['org', 'display', '--target-org', orgAlias, '--json']);
        
        if (!result.success) {
            return null;
        }

        try {
            const data = JSON.parse(result.stdout);
            const orgData = data.result;
            
            return {
                name: orgData.alias || orgData.username || 'Unknown',
                url: orgData.instanceUrl || 'Unknown',
                username: orgData.username || 'Unknown',
                id: orgData.id || 'Unknown'
            };
        } catch (e) {
            return null;
        }
    }

    async testToolingAPI(orgAlias) {
        const query = "SELECT COUNT() FROM ApexClass LIMIT 1";
        const result = await this.runSFCommand([
            'data', 'query', '--query', query,
            '--target-org', orgAlias,
            '--use-tooling-api', '--json'
        ]);
        
        return result.success;
    }

    async getCoverageData(orgAlias) {
        const response = {
            success: false,
            coverage: {},
            totalCovered: 0,
            totalUncovered: 0,
            overallPercentage: 0.0,
            error: null,
            toolingAPIUsed: false
        };

        // Test Tooling API availability
        const toolingAvailable = await this.testToolingAPI(orgAlias);
        response.toolingAPIUsed = toolingAvailable;

        let result;
        if (toolingAvailable) {
            // Use Tooling API for coverage data
            const query = `
                SELECT ApexClassOrTrigger.Name, NumLinesCovered, NumLinesUncovered 
                FROM ApexCodeCoverageAggregate 
                WHERE ApexClassOrTrigger.NamespacePrefix = null
                ORDER BY ApexClassOrTrigger.Name
            `;

            result = await this.runSFCommand([
                'data', 'query', '--query', query,
                '--target-org', orgAlias,
                '--use-tooling-api', '--json'
            ]);
        } else {
            // Fallback - just get class list
            const query = "SELECT Id, Name FROM ApexClass WHERE NamespacePrefix = null LIMIT 50";
            
            result = await this.runSFCommand([
                'data', 'query', '--query', query,
                '--target-org', orgAlias, '--json'
            ]);
        }

        if (!result.success) {
            response.error = `Query failed: ${result.stderr}`;
            return response;
        }

        try {
            const data = JSON.parse(result.stdout);
            const records = data.result?.records || [];

            if (toolingAvailable) {
                // Process coverage data
                records.forEach(record => {
                    const name = record.ApexClassOrTrigger?.Name;
                    if (name) {
                        const covered = record.NumLinesCovered || 0;
                        const uncovered = record.NumLinesUncovered || 0;
                        const total = covered + uncovered;

                        response.coverage[name] = {
                            covered,
                            uncovered,
                            total,
                            percentage: total > 0 ? Math.round((covered / total * 100) * 100) / 100 : 0.0
                        };

                        response.totalCovered += covered;
                        response.totalUncovered += uncovered;
                    }
                });
            } else {
                // Just show class list
                records.forEach(record => {
                    const name = record.Name;
                    if (name) {
                        response.coverage[name] = {
                            covered: 0,
                            uncovered: 0,
                            total: 0,
                            percentage: 0.0
                        };
                    }
                });
                response.error = "Tooling API not available - showing class list only";
            }

            const totalLines = response.totalCovered + response.totalUncovered;
            response.overallPercentage = totalLines > 0 ? 
                Math.round((response.totalCovered / totalLines * 100) * 100) / 100 : 0.0;
            
            response.success = true;

        } catch (e) {
            response.error = `Failed to parse data: ${e.message}`;
        }

        return response;
    }
}

module.exports = { SalesforceService };
