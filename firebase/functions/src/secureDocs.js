const { onRequest } = require('firebase-functions/v2/https');
const { initializeApp } = require('firebase-admin/app');
const { getAuth } = require('firebase-admin/auth');
const { getStorage } = require('firebase-admin/storage');
const cors = require('cors')({ origin: true });

// Initialize Firebase Admin
initializeApp();

/**
 * secureDocs - 2nd Generation Cloud Function
 * 
 * Provides authenticated access to documentation stored in GCS
 * All routes require valid session cookie authentication
 * 
 * Security Features:
 * - Session cookie validation via Firebase Admin SDK
 * - Audit logging for all access attempts
 * - Secure headers enforcement
 * - GCS streaming for private content delivery
 */
exports.secureDocs = onRequest({
  region: 'us-central1',
  memory: '256MiB',
  timeoutSeconds: 60,
  maxInstances: 100
}, async (req, res) => {
  return cors(req, res, async () => {
    try {
      // Security Headers
      res.set({
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains; preload',
        'X-Frame-Options': 'DENY',
        'X-Content-Type-Options': 'nosniff',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline' https://www.gstatic.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self'"
      });

      // Extract session cookie
      const sessionCookie = req.cookies?.__session;
      
      if (!sessionCookie) {
        console.log('No session cookie found, redirecting to login');
        return res.redirect('/login.html');
      }

      // Verify session cookie
      let decodedClaims;
      try {
        decodedClaims = await getAuth().verifySessionCookie(sessionCookie, true);
      } catch (error) {
        console.error('Session verification failed:', error.message);
        res.clearCookie('__session');
        return res.redirect('/login.html');
      }

      // Audit logging
      const auditLog = {
        timestamp: new Date().toISOString(),
        uid: decodedClaims.uid,
        email: decodedClaims.email,
        path: req.path,
        method: req.method,
        ip: req.ip,
        userAgent: req.get('User-Agent')
      };
      console.log('Audit:', JSON.stringify(auditLog));

      // Determine file path in GCS
      let filePath = req.path === '/' ? 'index.html' : req.path.substring(1);
      
      // Ensure .html extension for routes without extensions
      if (!filePath.includes('.') && !filePath.endsWith('/')) {
        filePath += '.html';
      }
      
      // Handle directory requests
      if (filePath.endsWith('/')) {
        filePath += 'index.html';
      }

      // Get file from GCS
      const bucket = getStorage().bucket(`${process.env.GCLOUD_PROJECT}-docs`);
      const file = bucket.file(`docs/prod/${filePath}`);

      try {
        const [exists] = await file.exists();
        
        if (!exists) {
          // Try fallback to index.html for SPA routing
          const indexFile = bucket.file('docs/prod/index.html');
          const [indexExists] = await indexFile.exists();
          
          if (indexExists) {
            return streamFile(indexFile, res, 'text/html');
          } else {
            return res.status(404).send('Documentation not found');
          }
        }

        // Determine content type
        const contentType = getContentType(filePath);
        return streamFile(file, res, contentType);

      } catch (error) {
        console.error('GCS access error:', error);
        return res.status(500).send('Internal server error');
      }

    } catch (error) {
      console.error('secureDocs error:', error);
      return res.status(500).send('Internal server error');
    }
  });
});

/**
 * Stream file from GCS to response
 */
async function streamFile(file, res, contentType) {
  try {
    const [metadata] = await file.getMetadata();
    
    res.set({
      'Content-Type': contentType,
      'Content-Length': metadata.size,
      'Cache-Control': 'public, max-age=300', // 5 minutes
      'ETag': metadata.etag
    });

    const stream = file.createReadStream();
    
    stream.on('error', (error) => {
      console.error('Stream error:', error);
      if (!res.headersSent) {
        res.status(500).send('File streaming error');
      }
    });

    stream.pipe(res);
    
  } catch (error) {
    console.error('File streaming error:', error);
    res.status(500).send('File access error');
  }
}

/**
 * Determine content type based on file extension
 */
function getContentType(filePath) {
  const ext = filePath.split('.').pop().toLowerCase();
  
  const contentTypes = {
    'html': 'text/html; charset=utf-8',
    'css': 'text/css',
    'js': 'application/javascript',
    'json': 'application/json',
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'gif': 'image/gif',
    'svg': 'image/svg+xml',
    'ico': 'image/x-icon',
    'pdf': 'application/pdf',
    'txt': 'text/plain',
    'md': 'text/markdown'
  };
  
  return contentTypes[ext] || 'application/octet-stream';
}
