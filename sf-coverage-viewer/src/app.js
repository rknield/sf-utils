/**
 * Main Application Class
 * Handles server initialization and routing
 */

const http = require('http');
const url = require('url');
const path = require('path');
const fs = require('fs');

const { SalesforceService } = require('./services/salesforce-service');
const { TemplateEngine } = require('./utils/template-engine');
const { AccessibilityHelpers } = require('./utils/accessibility-helpers');

class CoverageApp {
    constructor(config) {
        this.config = config;
        this.salesforceService = new SalesforceService(config.salesforce);
        this.templateEngine = new TemplateEngine();
        this.server = null;
        
        this.init();
    }

    async init() {
        console.log('🔍 Initializing Salesforce Coverage Viewer...');
        
        try {
            await this.salesforceService.initialize();
            this.startServer();
        } catch (error) {
            console.error('❌ Failed to initialize application:', error.message);
            process.exit(1);
        }
    }

    startServer() {
        this.server = http.createServer((req, res) => {
            this.handleRequest(req, res);
        });

        this.server.listen(this.config.server.port, this.config.server.host, () => {
            console.log(`🚀 ${this.config.app.name} running at:`);
            console.log(`   http://${this.config.server.host}:${this.config.server.port}`);
            console.log(`\n♿ Accessibility Features:`);
            console.log(`   • WCAG 2.1 AA compliant`);
            console.log(`   • Section 508 compliant`);
            console.log(`   • Screen reader optimized`);
            console.log(`   • Keyboard navigation support`);
            console.log(`\n⚡ Ready! Open your browser to the URL above.`);
        });
    }

    async handleRequest(req, res) {
        const parsedUrl = url.parse(req.url, true);
        const pathname = parsedUrl.pathname;

        // Set security headers
        this.setSecurityHeaders(res);

        try {
            // Route handling
            if (pathname === '/') {
                await this.handleHomePage(req, res);
            } else if (pathname === '/css/styles.css') {
                this.serveStaticFile(req, res, 'public/css/styles.css', 'text/css');
            } else if (pathname === '/js/app.js') {
                this.serveStaticFile(req, res, 'public/js/app.js', 'application/javascript');
            } else if (pathname.startsWith('/coverage/')) {
                const orgAlias = decodeURIComponent(pathname.split('/')[2]);
                await this.handleCoveragePage(req, res, orgAlias);
            } else if (pathname === '/api/orgs') {
                await this.handleAPIOrgs(req, res);
            } else if (pathname.startsWith('/api/coverage/')) {
                const orgAlias = decodeURIComponent(pathname.split('/')[3]);
                await this.handleAPICoverage(req, res, orgAlias);
            } else {
                this.send404(res);
            }
        } catch (error) {
            console.error('Request error:', error);
            this.sendError(res, 'Internal server error');
        }
    }

    setSecurityHeaders(res) {
        const security = this.config.security;
        res.setHeader('X-Content-Type-Options', 'nosniff');
        res.setHeader('X-Frame-Options', security.frameOptions);
        res.setHeader('X-XSS-Protection', security.xssProtection);
        res.setHeader('Content-Security-Policy', security.contentSecurityPolicy);
        res.setHeader('Access-Control-Allow-Origin', '*');
        res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
        res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    }

    async handleHomePage(req, res) {
        const orgs = await this.salesforceService.getAvailableOrgs();
        const templateData = {
            title: this.config.app.name,
            orgs: orgs,
            config: this.config
        };
        
        const html = await this.templateEngine.render('pages/home', templateData);
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(html);
    }

    async handleCoveragePage(req, res, orgAlias) {
        const orgInfo = await this.salesforceService.getOrgInfo(orgAlias);
        if (!orgInfo) {
            return this.sendOrgNotFound(res, orgAlias);
        }

        const coverageData = await this.salesforceService.getCoverageData(orgAlias);
        const templateData = {
            title: `Coverage Report: ${orgInfo.name}`,
            orgInfo: orgInfo,
            coverageData: coverageData,
            config: this.config
        };
        
        const html = await this.templateEngine.render('pages/coverage', templateData);
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end(html);
    }

    async handleAPIOrgs(req, res) {
        const orgs = await this.salesforceService.getAvailableOrgs();
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify(orgs, null, 2));
    }

    async handleAPICoverage(req, res, orgAlias) {
        const coverageData = await this.salesforceService.getCoverageData(orgAlias);
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify(coverageData, null, 2));
    }

    serveStaticFile(req, res, filePath, contentType) {
        const fullPath = path.join(__dirname, '..', filePath);
        
        fs.readFile(fullPath, (err, data) => {
            if (err) {
                this.send404(res);
                return;
            }
            
            res.writeHead(200, { 'Content-Type': contentType });
            res.end(data);
        });
    }

    sendOrgNotFound(res, orgAlias) {
        const templateData = {
            title: 'Organization Not Found',
            orgAlias: orgAlias,
            config: this.config
        };
        
        this.templateEngine.render('pages/error', templateData).then(html => {
            res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
            res.end(html);
        });
    }

    send404(res) {
        const templateData = {
            title: '404 - Page Not Found',
            error: 'The requested page could not be found.',
            config: this.config
        };
        
        this.templateEngine.render('pages/error', templateData).then(html => {
            res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
            res.end(html);
        });
    }

    sendError(res, message) {
        const templateData = {
            title: 'Server Error',
            error: message,
            config: this.config
        };
        
        this.templateEngine.render('pages/error', templateData).then(html => {
            res.writeHead(500, { 'Content-Type': 'text/html; charset=utf-8' });
            res.end(html);
        });
    }

    stop(callback) {
        if (this.server) {
            this.server.close(callback);
        } else if (callback) {
            callback();
        }
    }
}

module.exports = { CoverageApp };
