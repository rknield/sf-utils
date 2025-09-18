/**
 * Application Configuration
 */

module.exports = {
    // Server configuration
    server: {
        port: process.env.PORT || 3000,
        host: process.env.HOST || 'localhost'
    },
    
    // Application settings
    app: {
        name: 'Salesforce Coverage Viewer',
        version: '1.0.0',
        description: 'Section 508 compliant code coverage viewer for Salesforce',
        author: 'Your Organization'
    },
    
    // Security settings
    security: {
        contentSecurityPolicy: "default-src 'self' 'unsafe-inline'",
        frameOptions: 'DENY',
        noSniff: true,
        xssProtection: '1; mode=block'
    },
    
    // Accessibility settings
    accessibility: {
        skipLinksEnabled: true,
        ariaLiveRegions: true,
        keyboardNavigation: true,
        highContrastSupport: true
    },
    
    // Salesforce CLI settings
    salesforce: {
        commandTimeout: 30000,
        maxRetries: 3,
        apiVersion: '65.0'
    }
};
