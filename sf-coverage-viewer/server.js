#!/usr/bin/env node
/**
 * Salesforce Coverage Viewer Server
 * Section 508 Compliant Web Application
 * 
 * Entry point for the application
 */

const { CoverageApp } = require('./src/app');
const config = require('./config/app-config');

// Initialize and start the application
const app = new CoverageApp(config);

// Graceful shutdown handling
process.on('SIGINT', () => {
    console.log('\n🛑 Shutting down server...');
    app.stop(() => {
        console.log('✅ Server stopped.');
        process.exit(0);
    });
});

process.on('SIGTERM', () => {
    console.log('\n🛑 Received SIGTERM, shutting down...');
    app.stop(() => {
        process.exit(0);
    });
});

// Handle uncaught exceptions
process.on('uncaughtException', (err) => {
    console.error('Uncaught Exception:', err);
    process.exit(1);
});

process.on('unhandledRejection', (reason, promise) => {
    console.error('Unhandled Rejection at:', promise, 'reason:', reason);
    process.exit(1);
});
