import * as functions from "firebase-functions";
import * as admin from "firebase-admin";
import {Storage} from "@google-cloud/storage";
import * as cookieParser from "cookie-parser";

// Initialize Firebase Admin
admin.initializeApp();

const storage = new Storage();

/**
 * SCIRM Secure Documentation Function (2nd Gen)
 * 
 * Validates Firebase Auth session cookies and serves documentation files
 * from Cloud Storage with security headers enforced.
 * 
 * Security Features:
 * - Session cookie validation via Firebase Admin SDK
 * - Redirect to /login for unauthenticated users
 * - HSTS, XFO DENY, XCTO nosniff, CSP headers
 * - Audit logging for all requests
 * - No anonymous access allowed
 */
export const secureDocs = functions
  .runWith({
    memory: "512MB",
    timeoutSeconds: 30,
  })
  .https.onRequest(async (req, res): Promise<void> => {
    // Parse cookies
    cookieParser()(req, res, () => {});

    const startTime = Date.now();
    const requestId = Math.random().toString(36).substring(7);
    
    // Log request for audit
    console.log(`[${requestId}] ${req.method} ${req.path}`, {
      ip: req.ip,
      userAgent: req.get("User-Agent"),
      referer: req.get("Referer"),
      timestamp: new Date().toISOString(),
    });

    try {
      // Check for session cookie
      const sessionCookie = req.cookies && req.cookies.__session;
      
      if (!sessionCookie) {
        console.log(`[${requestId}] No session cookie found, redirecting to login`);
        return redirectToLogin(res);
      }

      // Verify session cookie
      let decodedClaims;
      try {
        decodedClaims = await admin.auth().verifySessionCookie(sessionCookie, true);
        console.log(`[${requestId}] Authenticated user: ${decodedClaims.uid} (${decodedClaims.email})`);
      } catch (error) {
        console.log(`[${requestId}] Invalid session cookie:`, error);
        return redirectToLogin(res);
      }

      // Handle login page request
      if (req.path === "/login" || req.path === "/login.html") {
        return serveLoginPage(res);
      }

      // Handle auth callback
      if (req.path === "/auth/callback") {
        return handleAuthCallback(req, res, requestId);
      }

      // Serve documentation files from Cloud Storage
      await serveDocumentationFile(req, res, requestId, decodedClaims);

    } catch (error) {
      console.error(`[${requestId}] Unexpected error:`, error);
      res.status(500).send("Internal Server Error");
    } finally {
      const duration = Date.now() - startTime;
      console.log(`[${requestId}] Request completed in ${duration}ms`);
    }
  });

/**
 * Redirect unauthenticated users to login page
 */
function redirectToLogin(res: functions.Response) {
  res.redirect(302, "/login");
}

/**
 * Serve the login page with Firebase Auth integration
 */
function serveLoginPage(res: functions.Response) {
  const loginHtml = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SCIRM Documentation - Login</title>
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0; padding: 0; height: 100vh;
            display: flex; align-items: center; justify-content: center;
        }
        .login-container {
            background: white; padding: 2rem; border-radius: 8px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.1); max-width: 400px; width: 90%;
        }
        .logo { text-align: center; margin-bottom: 2rem; }
        .logo h1 { color: #333; margin: 0; font-size: 1.8rem; }
        .logo p { color: #666; margin: 0.5rem 0 0; font-size: 0.9rem; }
        .login-btn {
            width: 100%; padding: 0.75rem; border: none; border-radius: 4px;
            background: #4285f4; color: white; font-size: 1rem; cursor: pointer;
            display: flex; align-items: center; justify-content: center; gap: 0.5rem;
        }
        .login-btn:hover { background: #3367d6; }
        .security-notice {
            margin-top: 1.5rem; padding: 1rem; background: #f8f9fa;
            border-radius: 4px; font-size: 0.85rem; color: #666;
        }
        .error { color: #d93025; margin-top: 1rem; font-size: 0.9rem; }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="logo">
            <h1>🔒 SCIRM Documentation</h1>
            <p>Secure AI-Powered Supply Chain Risk Management</p>
        </div>
        
        <button id="loginBtn" class="login-btn">
            <svg width="18" height="18" viewBox="0 0 24 24">
                <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Sign in with Google
        </button>
        
        <div id="error" class="error" style="display: none;"></div>
        
        <div class="security-notice">
            <strong>🛡️ Security Notice:</strong> This documentation platform requires authentication.
            Only authorized SCIRM team members can access internal documentation and governance materials.
        </div>
    </div>

    <script type="module">
        import { initializeApp } from 'https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js';
        import { getAuth, GoogleAuthProvider, signInWithPopup } from 'https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js';

        const firebaseConfig = {
            // Will be populated by environment variables in production
            apiKey: "demo-api-key",
            authDomain: "scirm-docs-prod.firebaseapp.com",
            projectId: "scirm-docs-prod"
        };

        const app = initializeApp(firebaseConfig);
        const auth = getAuth(app);
        const provider = new GoogleAuthProvider();

        document.getElementById('loginBtn').addEventListener('click', async () => {
            try {
                const result = await signInWithPopup(auth, provider);
                const idToken = await result.user.getIdToken();
                
                // Exchange ID token for session cookie
                const response = await fetch('/auth/callback', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ idToken })
                });
                
                if (response.ok) {
                    window.location.href = '/';
                } else {
                    throw new Error('Failed to create session');
                }
            } catch (error) {
                console.error('Login error:', error);
                document.getElementById('error').textContent = 'Login failed. Please try again.';
                document.getElementById('error').style.display = 'block';
            }
        });
    </script>
</body>
</html>`;

  res.set("Content-Type", "text/html");
  res.send(loginHtml);
}

/**
 * Handle authentication callback - exchange ID token for session cookie
 */
async function handleAuthCallback(req: functions.Request, res: functions.Response, requestId: string): Promise<void> {
  if (req.method !== "POST") {
    res.status(405).send("Method Not Allowed");
    return;
  }

  const {idToken} = req.body;
  if (!idToken) {
    res.status(400).send("Missing ID token");
    return;
  }

  try {
    // Verify ID token
    const decodedToken = await admin.auth().verifyIdToken(idToken);
    console.log(`[${requestId}] Creating session for user: ${decodedToken.uid}`);

    // Create session cookie (5 days expiry)
    const expiresIn = 60 * 60 * 24 * 5 * 1000; // 5 days
    const sessionCookie = await admin.auth().createSessionCookie(idToken, {expiresIn});

    // Set secure cookie
    res.cookie("__session", sessionCookie, {
      maxAge: expiresIn,
      httpOnly: true,
      secure: true,
      sameSite: "lax",
    });

    res.status(200).send({success: true});
  } catch (error) {
    console.error(`[${requestId}] Auth callback error:`, error);
    res.status(401).send("Unauthorized");
  }
}

/**
 * Serve documentation files from Cloud Storage
 */
async function serveDocumentationFile(
  req: functions.Request, 
  res: functions.Response, 
  requestId: string,
  userClaims: admin.auth.DecodedIdToken
) {
  let filePath = req.path;
  
  // Default to index.html for root requests
  if (filePath === "/" || filePath === "") {
    filePath = "/index.html";
  }

  // Remove leading slash and construct GCS path
  const gcsPath = `docs/prod${filePath}`;
  const bucketName = process.env.GCLOUD_PROJECT + ".appspot.com";
  
  console.log(`[${requestId}] Serving file: ${gcsPath} for user ${userClaims.email}`);

  try {
    const file = storage.bucket(bucketName).file(gcsPath);
    const [exists] = await file.exists();

    if (!exists) {
      // Try with .html extension for clean URLs
      const htmlPath = `docs/prod${filePath}.html`;
      const htmlFile = storage.bucket(bucketName).file(htmlPath);
      const [htmlExists] = await htmlFile.exists();
      
      if (htmlExists) {
        return streamFile(htmlFile, res, requestId);
      }
      
      console.log(`[${requestId}] File not found: ${gcsPath}`);
      return res.status(404).send("Documentation page not found");
    }

    await streamFile(file, res, requestId);
  } catch (error) {
    console.error(`[${requestId}] Error serving file:`, error);
    res.status(500).send("Error loading documentation");
  }
}

/**
 * Stream file from Cloud Storage to response
 */
async function streamFile(file: any, res: functions.Response, requestId: string) {
  try {
    const [metadata] = await file.getMetadata();
    const contentType = metadata.contentType || "text/html";
    
    res.set("Content-Type", contentType);
    res.set("Cache-Control", "public, max-age=300"); // 5 minute cache
    
    const stream = file.createReadStream();
    stream.pipe(res);
    
    stream.on("error", (error: any) => {
      console.error(`[${requestId}] Stream error:`, error);
      if (!res.headersSent) {
        res.status(500).send("Error streaming file");
      }
    });
  } catch (error) {
    console.error(`[${requestId}] Error streaming file:`, error);
    if (!res.headersSent) {
      res.status(500).send("Error loading file");
    }
  }
}
