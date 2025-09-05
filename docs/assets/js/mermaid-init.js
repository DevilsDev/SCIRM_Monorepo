/**
 * Mermaid.js Initialization for SCIRM Documentation
 * 
 * Initializes Mermaid with secure configuration for local rendering
 * without requiring inline scripts (CSP compliant).
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize Mermaid with secure configuration
    mermaid.initialize({
        startOnLoad: true,
        securityLevel: 'loose', // Required for node styling (fill colors, etc.)
        theme: 'default',
        themeVariables: {
            primaryColor: '#1976d2',
            primaryTextColor: '#fff',
            primaryBorderColor: '#1565c0',
            lineColor: '#333',
            sectionBkgColor: '#f5f5f5',
            altSectionBkgColor: '#e3f2fd',
            gridColor: '#ddd',
            secondaryColor: '#ff9800',
            tertiaryColor: '#4caf50'
        },
        flowchart: {
            useMaxWidth: true,
            htmlLabels: true,
            curve: 'basis'
        },
        sequence: {
            useMaxWidth: true,
            diagramMarginX: 50,
            diagramMarginY: 10,
            actorMargin: 50,
            width: 150,
            height: 65,
            boxMargin: 10,
            boxTextMargin: 5,
            noteMargin: 10,
            messageMargin: 35,
            mirrorActors: true,
            bottomMarginAdj: 1,
            useMaxWidth: true,
            rightAngles: false,
            showSequenceNumbers: false
        },
        gantt: {
            useMaxWidth: true,
            leftPadding: 75,
            gridLineStartPadding: 35,
            fontSize: 11,
            fontFamily: '"Open Sans", sans-serif',
            sectionFontSize: 24,
            numberSectionStyles: 4
        },
        journey: {
            useMaxWidth: true
        },
        timeline: {
            useMaxWidth: true
        },
        gitgraph: {
            useMaxWidth: true,
            mainBranchName: 'main',
            showBranches: true,
            showCommitLabel: true,
            rotateCommitLabel: true
        },
        c4: {
            useMaxWidth: true,
            diagramMarginX: 50,
            diagramMarginY: 10,
            c4ShapeMargin: 50,
            c4ShapeInRow: 4,
            c4BoundaryInRow: 2,
            personFontSize: 14,
            personFontFamily: '"Open Sans", sans-serif',
            personFontWeight: 'normal',
            external_personFontSize: 14,
            external_personFontFamily: '"Open Sans", sans-serif',
            external_personFontWeight: 'normal',
            systemFontSize: 14,
            systemFontFamily: '"Open Sans", sans-serif',
            systemFontWeight: 'normal',
            external_systemFontSize: 14,
            external_systemFontFamily: '"Open Sans", sans-serif',
            external_systemFontWeight: 'normal'
        }
    });

    // Log successful initialization for debugging
    console.log('Mermaid.js initialized successfully for SCIRM documentation');
    
    // Force re-render of any existing diagrams
    if (typeof mermaid.init === 'function') {
        mermaid.init(undefined, document.querySelectorAll('.mermaid'));
    }
});
