
# =============================================================================
# Salesforce Coverage Viewer - Node.js Application
# =============================================================================

## Installation & Setup

1. Extract/clone this application structure
2. Navigate to the sf-coverage-viewer directory
3. Run: node server.js
4. Open: http://localhost:3000

## Application Structure

sf-coverage-viewer/
├── server.js                 # Main entry point
├── package.json              # Package configuration
├── config/
│   └── app-config.js         # Application configuration
├── src/
│   ├── app.js                # Main application class
│   ├── services/
│   │   └── salesforce-service.js  # SF CLI integration
│   ├── controllers/          # Route controllers (future)
│   └── utils/                # Utility classes
├── public/
│   ├── css/
│   │   └── styles.css        # Section 508 compliant styles
│   ├── js/
│   │   └── app.js           # Client-side JavaScript
│   └── images/              # Static images
├── views/
│   ├── pages/               # Page templates
│   └── components/          # Reusable components
└── docs/                    # Documentation

## Features

✅ Section 508 / WCAG 2.1 AA compliant
✅ Professional Node.js application structure  
✅ Modular, maintainable codebase
✅ No external dependencies
✅ Read-only Salesforce access
✅ Auto SF CLI detection
✅ Custom styling hooks

## Next Steps

Run the setup script above to create the complete application structure.
Additional files (templates, CSS, client JS) will be created automatically.


